"""Real nearby-place lookup for market investigation (OpenStreetMap; no API key).

Geocoding: Nominatim. Nearby places: Overpass API. Results are real public map data, cached in
data/output/places/ so a live demo does not hammer the free services (Nominatim allows ~1 request/s).
Nothing here contacts a business; it only reads public map data.
"""
from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "EnterpriseBuddy-hackathon-demo/1.0 (student project; synthetic business)"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

KINDS = {
    # similar stores / competitors of a campus snack seller
    "competitors": [('shop', 'bakery|confectionery|pastry|deli'), ('amenity', 'cafe|fast_food|food_court'),
                    ('shop', 'beverages|tea|coffee')],
    # places a seller can buy raw materials offline
    "suppliers": [('shop', 'wholesale|supermarket|convenience|greengrocer|butcher|bakery_supplies|kitchen|packaging|frozen_food'),
                  ('shop', 'general|department_store')],
}

_last_call = [0.0]


def _get(url: str, data: bytes | None = None, timeout=40):
    wait = 1.1 - (time.time() - _last_call[0])
    if "nominatim" in url and wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "place"


def geocode(query: str, country="my"):
    params = {"q": query, "format": "json", "limit": 1, "addressdetails": 1}
    if country:
        params["countrycodes"] = country
    rows = _get(NOMINATIM + "?" + urllib.parse.urlencode(params))
    if not rows:
        return None
    r = rows[0]
    return {"query": query, "name": r.get("display_name"), "lat": float(r["lat"]), "lon": float(r["lon"])}


def distance_m(a_lat, a_lon, b_lat, b_lon):
    p = math.pi / 180
    h = (math.sin((b_lat - a_lat) * p / 2) ** 2 +
         math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin((b_lon - a_lon) * p / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _address(tags: dict) -> str:
    parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:suburb") or tags.get("addr:city"),
             tags.get("addr:postcode")]
    return ", ".join(p for p in parts if p) or tags.get("addr:full", "")


def nearby(query: str, kind="competitors", radius_m=2000, limit=60, cache_dir: Path | None = None):
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    cache = cache_dir / f"{slug(query)}__{kind}__{radius_m}.json" if cache_dir else None
    if cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    center = geocode(query)
    if not center:
        return {"query": query, "kind": kind, "error": f"Could not find '{query}' on the map. Try a fuller name, e.g. 'Universiti Malaya, Kuala Lumpur'."}
    lat, lon = center["lat"], center["lon"]
    parts = "".join(f'nwr["{k}"~"^({v})$"]["name"](around:{radius_m},{lat},{lon});' for k, v in KINDS[kind])
    q = f"[out:json][timeout:30];({parts});out center {limit * 2};"
    data, err = None, None
    for ep in OVERPASS + OVERPASS[:1]:
        try:
            data = _get(ep, urllib.parse.urlencode({"data": q}).encode())
            break
        except Exception as exc:  # busy or down: try the next mirror
            err = exc
            time.sleep(1)
    if data is None:
        return {"query": query, "kind": kind, "center": center, "error": f"Map search service unavailable: {err}"}
    places, seen = [], set()
    for e in data.get("elements", []):
        t = e.get("tags", {})
        plat = e.get("lat") or e.get("center", {}).get("lat")
        plon = e.get("lon") or e.get("center", {}).get("lon")
        if plat is None or not t.get("name"):
            continue
        key = (t["name"].lower(), round(plat, 4), round(plon, 4))
        if key in seen:
            continue
        seen.add(key)
        category = t.get("shop") or t.get("amenity") or ""
        places.append({
            "name": t["name"], "category": category.replace("_", " "), "lat": plat, "lon": plon,
            "distance_m": round(distance_m(lat, lon, plat, plon)),
            "address": _address(t), "opening_hours": t.get("opening_hours", ""),
            "phone": t.get("phone") or t.get("contact:phone", ""), "website": t.get("website") or t.get("contact:website", ""),
            "brand": t.get("brand", ""), "cuisine": t.get("cuisine", "").replace(";", ", "),
            "osm_url": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
            "directions_url": f"https://www.google.com/maps/dir/?api=1&destination={plat},{plon}",
        })
    places.sort(key=lambda p: p["distance_m"])
    places = places[:limit]
    cats: dict[str, int] = {}
    for p in places:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    result = {"query": query, "kind": kind, "radius_m": radius_m, "center": center, "count": len(places),
              "by_category": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
              "independent_count": sum(1 for p in places if not p["brand"]),
              "source": "OpenStreetMap contributors (Nominatim + Overpass API)", "places": places,
              "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
