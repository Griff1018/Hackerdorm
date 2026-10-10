"""Supplier listing scraper: product image, item name, price, and online/offline ordering signals.

Reads the public product page saved in supplier_research.csv (or any URL the owner gives), extracts
structured data (JSON-LD Product, OpenGraph, product meta tags) with a visible-text fallback, and
downloads the product image locally so the demo does not depend on hot-linking. It never logs in,
adds to cart, or contacts the supplier. Prices found here are "listed price on <date>", not quotes.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0 Safari/537.36")
STATES = ("Selangor|Kuala Lumpur|Johor|Penang|Pulau Pinang|Perak|Kedah|Kelantan|Terengganu|Pahang|Negeri Sembilan|"
          "Melaka|Malacca|Sabah|Sarawak|Perlis|Putrajaya|Labuan")
ONLINE_SIGNS = [r"add[\s_-]*to[\s_-]*(cart|bag|basket)", r"buy[\s_-]*now", r"checkout", r"woocommerce", r"shopify",
                r"add-to-cart", r"order online", r"shop now", r"in stock"]
OFFLINE_SIGNS = [r"walk[\s-]*in", r"visit (our|the) (store|shop|outlet|showroom)", r"our (outlets?|branches|showroom)",
                 r"opening hours", r"operating hours", r"business hours", r"self[\s-]*(pick[\s-]*up|collect)", r"store locator"]
DELIVERY_SIGNS = [r"deliver(y|ies)", r"shipping", r"lalamove", r"courier", r"nationwide"]
MARKETPLACES = {"shopee": "Shopee", "lazada": "Lazada", "supplybunny": "SupplyBunny", "borong": "Borong",
                "alibaba": "Alibaba", "grab": "GrabMart", "foodpanda": "pandamart"}


def fetch(url: str, timeout=25) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-MY,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(3_000_000)
        charset = r.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace"), r.geturl()


def _meta(page: str, *names) -> str:
    for n in names:
        m = re.search(r'<meta[^>]+(?:property|name|itemprop)=["\']%s["\'][^>]*content=["\']([^"\']+)' % re.escape(n), page, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\']%s["\']' % re.escape(n), page, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def _jsonld_products(page: str):
    out = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                t = d.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    out.append(d)
                stack.extend(v for v in d.values() if isinstance(v, (list, dict)))
    return out


def _visible_text(page: str) -> str:
    page = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def _first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v


def parse_listing(page: str, url: str) -> dict:
    text = _visible_text(page)
    low_page = page.lower()
    name = image = price = currency = availability = ""
    how = []
    for p in _jsonld_products(page):
        name = name or str(p.get("name", ""))
        img = _first(p.get("image"))
        image = image or (img.get("url", "") if isinstance(img, dict) else str(img or ""))
        offers = _first(p.get("offers")) or {}
        if isinstance(offers, dict):
            price = price or str(offers.get("price") or offers.get("lowPrice") or "")
            currency = currency or str(offers.get("priceCurrency") or "")
            availability = availability or str(offers.get("availability") or "").rsplit("/", 1)[-1]
        if price:
            how.append("structured data (JSON-LD)")
    if not name:
        name = _meta(page, "og:title", "twitter:title") or (re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I) or [None, ""])[1].strip()
    if not image:
        image = _meta(page, "og:image", "og:image:secure_url", "twitter:image")
    if price and re.fullmatch(r"0+(\.0+)?", price.strip()):
        price, how = "", []
    if not price:
        price = _meta(page, "product:price:amount", "og:price:amount", "price")
        currency = currency or _meta(page, "product:price:currency", "og:price:currency", "priceCurrency")
        if price:
            how.append("product meta tags")
    if not price:
        promo = re.compile(r"(shipping|above|over|min(imum)?|spend|free|save|off|delivery|voucher|discount|up to)\W*$", re.I)
        for m in re.finditer(r"\bRM\s?(\d{1,5}(?:,\d{3})*(?:\.\d{2})?)", text):
            if not promo.search(text[max(0, m.start() - 40):m.start()]):
                price, currency = m.group(1).replace(",", ""), "MYR"
                how.append("page text (unconfirmed - check on page)")
                break
    candidates = [image, _meta(page, "og:image", "og:image:secure_url", "twitter:image")]
    candidates = list(dict.fromkeys(urllib.parse.urljoin(url, html.unescape(c)) for c in candidates if c))
    image = candidates[0] if candidates else ""
    name = html.unescape(re.sub(r"\s+", " ", name)).strip()[:160]

    def hits(patterns, hay):
        return sorted({re.search(p, hay, re.I).group(0).lower() for p in patterns if re.search(p, hay, re.I)})
    online_hits = hits(ONLINE_SIGNS, low_page)
    offline_hits = hits(OFFLINE_SIGNS, text)
    delivery_hits = hits(DELIVERY_SIGNS, text)
    host = urllib.parse.urlparse(url).netloc.lower()
    marketplace = next((v for k, v in MARKETPLACES.items() if k in host), "")
    addr = ""
    m = re.search(r"([A-Z0-9][^.;|]{10,120}?\b\d{5}\b[^.;|]{0,40}?\b(?:%s)\b)" % STATES, text)
    if m:
        addr = m.group(1).strip()[-160:]
    pm = re.search(r"(?:\+?6?0)1\d[-\s]?\d{3,4}[-\s]?\d{4}|\+?60[-\s]?\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}", text)
    phone = pm.group(0) if pm else ""
    online = bool(online_hits) or bool(marketplace)
    offline = bool(offline_hits) or bool(addr)
    return {
        "item_name": name, "image_url": image, "image_candidates": candidates, "listed_price": price, "currency": currency or ("MYR" if price else ""),
        "availability": availability, "price_method": ", ".join(dict.fromkeys(how)) or "not found on page",
        "online_order": online, "offline_purchase": offline, "delivery_mentioned": bool(delivery_hits),
        "marketplace": marketplace, "address_found": addr, "phone_found": phone or "",
        "evidence": {"online_signals": online_hits + ([f"listed on {marketplace}"] if marketplace else []),
                     "offline_signals": offline_hits + (["address on page"] if addr else []), "delivery_signals": delivery_hits},
    }


def download_image(image_url: str, dest_dir: Path) -> str:
    if not image_url:
        return ""
    data = b""
    for attempt in range(3):
        try:
            req = urllib.request.Request(image_url, headers={"User-Agent": BROWSER_UA, "Referer": image_url})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read(4_000_000)
            break
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    # identify by file signature; some servers send a wrong Content-Type
    if data[:3] == b"\xff\xd8\xff":
        ext = ".jpg"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        ext = ".png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        ext = ".webp"
    elif data[:4] == b"GIF8":
        ext = ".gif"
    else:
        return ""
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / (hashlib.sha1(image_url.encode()).hexdigest()[:16] + ext)
    path.write_bytes(data)
    return path.as_posix()


def scrape(url: str, image_dir: Path | None = None) -> dict:
    row = {"source_url": url, "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        page, final = fetch(url)
    except Exception as exc:
        row.update({"ok": False, "error": f"page could not be read: {exc}"})
        return row
    row.update(parse_listing(page, final), ok=True, final_url=final)
    if image_dir:
        for cand in row.get("image_candidates", []):
            local = download_image(cand, image_dir)
            if local:
                row["image_local"], row["image_url"] = local, cand
                break
    return row


def scrape_suppliers(root: Path, only_material: str | None = None, workers=4) -> dict:
    """Scrape every source_url in supplier_research.csv; merge with the deterministic scores."""
    from concurrent.futures import ThreadPoolExecutor
    out = root / "data" / "output"
    rows = list(csv.DictReader((out / "supplier_research.csv").open(newline="", encoding="utf-8-sig")))
    if only_material:
        rows = [r for r in rows if r["material_name"].lower() == only_material.lower()]
    urls = sorted({r["source_url"] for r in rows if r.get("source_url", "").startswith("http")})
    img_dir = out / "supplier_images"
    with ThreadPoolExecutor(workers) as ex:
        scraped = dict(zip(urls, ex.map(lambda u: scrape(u, img_dir), urls)))
    listings = []
    for r in rows:
        s = scraped.get(r["source_url"], {})
        local = s.get("image_local", "")
        listings.append({
            "material": r["material_name"], "supplier": r["supplier_name"], "score": r["score"], "tier": r["tier"],
            "rank": r["rank"], "recommended": r["recommended"], "saved_price": r["listed_price"], "price_unit": r["price_unit"],
            "location": r["location"], "notes": r["notes"], "source_url": r["source_url"],
            "scrape_ok": s.get("ok", False), "scrape_error": s.get("error", ""),
            "item_name": s.get("item_name", ""), "listed_price_now": s.get("listed_price", ""), "currency": s.get("currency", ""),
            "price_method": s.get("price_method", ""), "availability": s.get("availability", ""),
            "image_url": s.get("image_url", ""),
            "image_local": Path(local).relative_to(root).as_posix() if local else "",
            "online_order": s.get("online_order", False), "offline_purchase": s.get("offline_purchase", False),
            "delivery_mentioned": s.get("delivery_mentioned", False), "marketplace": s.get("marketplace", ""),
            "address_found": s.get("address_found", ""), "evidence": s.get("evidence", {}),
            "retrieved_at": s.get("retrieved_at", ""),
        })
    listings.sort(key=lambda x: (x["material"], -(float(x["score"]) if x["score"] else -1)))
    doc = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "count": len(listings),
           "scraped_ok": sum(1 for v in scraped.values() if v.get("ok")), "pages": len(urls),
           "note": "Listed prices are what the public page showed at retrieval time; confirm with the supplier before paying.",
           "listings": listings}
    (out / "supplier_listings.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc
