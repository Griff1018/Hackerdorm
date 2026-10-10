"""Build data/output/supplier_research_input.csv from the raw research record.

Why this file exists
--------------------
Section G.11 says the supplier score must be computed by CODE from the recorded fields,
never estimated by the model. That applies to the price normalisation too: this script
divides the listed price by the pack size the source actually stated, so no per-kg,
per-litre or per-100-pieces figure in the output was produced by hand.

What is recorded here is only what each source actually stated.
A field the source does not state is left blank and the reason is written in `notes`.
Nothing here is a quote, an order, or a payment - it is research for comparison only.
"""
from __future__ import annotations

import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "output" / "supplier_research_raw.csv"
OUT = ROOT / "data" / "output" / "supplier_research_input.csv"

# Every finding below was retrieved on 2026-10-10 (see RETRIEVED_AT).
RETRIEVED_AT = "2026-10-10T14:05:00+08:00"

RAW_COLUMNS = [
    "material_name", "tier", "supplier_name", "product_name",
    "listed_price", "currency", "pack_qty", "pack_unit", "comparable_basis",
    "minimum_order_qty", "minimum_order_unit", "delivery_or_lead_time",
    "seller_type", "listing_updated_within_90d", "location",
    "available", "material_match", "source_url", "retrieved_at", "notes",
]

# basis -> (base unit, multiplier applied to the stated pack quantity)
BASIS = {
    "kg": ("kg", Decimal(1)),
    "g": ("kg", Decimal("0.001")),
    "litre": ("litre", Decimal(1)),
    "ml": ("litre", Decimal("0.001")),
    "100 pcs": ("100 pcs", Decimal("0.01")),
    "pcs": ("100 pcs", Decimal("0.01")),
}

ROWS: list[dict] = [
    # ---------------------------------------------------------------- FULL TIER
    dict(material_name="Chocolate chips", tier="full",
         supplier_name="Pastry Pro Retail Sdn Bhd (listed on SupplyBunny)",
         product_name="Chocolate Chips - Compound White 1kg/pack",
         listed_price="25.75", currency="MYR", pack_qty="1", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Klang Valley, Malaysia",
         source_url="https://www.supplybunny.com/en/products/chocolate-chips-compound-white-1kg-pack",
         notes="Unbranded compound (not couverture) white chips. Page states 'Quote in 2-4h'. No minimum order and no delivery time published on the page - both left blank, not guessed."),

    dict(material_name="Chocolate chips", tier="full",
         supplier_name="Marubishi Malaysia",
         product_name="Lecker White Compound Chocolate Chips (1kg x 10pkts x ctn)",
         listed_price="29.00", currency="MYR", pack_qty="1", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Malaysia",
         source_url="https://marubishi-group.com/products/lecker-white-compound-chips-1kg",
         notes="AMBIGUOUS PRICE BASIS: the title bundles 10 pkts per carton but only one RM29.00 price is shown; recorded as the 1 kg packet price because the page's only pack statement is 'Packing: 1kg per packet'. Origin Malaysia, halal certified. Confirm the basis with the supplier before ordering."),

    dict(material_name="Chocolate chips", tier="full",
         supplier_name="Healthy Baker Malaysia",
         product_name="Premium Dark Chocolate Chip 1kg",
         listed_price="19.90", currency="MYR", pack_qty="1", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Malaysia",
         source_url="https://www.healthybakermalaysia.com/product/premium-dark-chocolate-chip-coklat-chip-baking-chocolate-chips-premium-halal-wholesale-price",
         notes="Retail/consumer listing (page shows '4 sold' and consumer vouchers), NOT a wholesale price - included only as a price reference. Page price range RM3.90-RM19.90 for 100g-1kg; RM19.90 is the 1 kg option. Country of origin Malaysia, halal stated in the listing title."),

    dict(material_name="Butter", tier="full",
         supplier_name="Pastry Pro Retail Sdn Bhd (listed on SupplyBunny)",
         product_name="Pastarom Bake Butter (H) 1kg/bottle",
         listed_price="55.55", currency="MYR", pack_qty="1", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Klang Valley, Malaysia",
         source_url="https://www.supplybunny.com/en/products/pastarom-bake-butter-h-1kg-bottle",
         material_match="no",
         notes="NOT block butter: the page describes it as 'Bake stable flavourings for yeast doughs, danish pastries, cakes and cookies'. The only bake-stable butter-type item on SupplyBunny in this search. No MOQ or delivery time published."),

    dict(material_name="Butter", tier="full",
         supplier_name="Buttercup & SCS (listed on Borong)",
         product_name="Plastic Tub Buttercup Luxury Spread 1 KG x 12",
         listed_price="236.16", currency="MYR", pack_qty="12", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="12", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/buttercup-and-scs/product/Plastic-Tub-Buttercup-Luxury-Spread-1-KG-x-12-Free-Delivery-Semenanjung-Malaysia/135701",
         material_match="no",
         notes="Spread (blended), not pure butter. Listing states free delivery to Semenanjung Malaysia. Delivery time is the Borong marketplace 3-5 day promise, not a per-seller promise. Minimum order = the 12 kg carton as listed."),

    dict(material_name="Butter", tier="full",
         supplier_name="e-Petani (listed on Borong)",
         product_name="Emborg Cook & Bake Buttery 250g",
         listed_price="9.00", currency="MYR", pack_qty="250", pack_unit="g", comparable_basis="kg",
         minimum_order_qty="250", minimum_order_unit="g", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/e-petani/product/Emborg-Cook-Bake-Buttery-250g-KLANG-VALLEY-ONLY/148640",
         material_match="no",
         notes="[KLANG VALLEY ONLY]. 'Buttery' blended product, not pure butter. Cheapest entry quantity of the four (250 g) but the most expensive per kg."),

    dict(material_name="Butter", tier="full",
         supplier_name="PJ Grocer Sdn Bhd (listed on Borong)",
         product_name="BUTTEROLL Fat Spread Unsalted Butter 10kg",
         listed_price="250.00", currency="MYR", pack_qty="10", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="10", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/pj-grocer/product/BUTTEROLL-Fat-Spread-Unsalted-Butter-10kg-KLANG-VALLEY-ONLY/136795",
         material_match="no",
         notes="[KLANG VALLEY ONLY]. Sold as 'Fat Spread Unsalted Butter' - a spread, not dairy butter. RRP MYR 300.00."),

    dict(material_name="Chicken filling", tier="full",
         supplier_name="SupplyBunny (frozen chicken supplier)",
         product_name="Halal Frozen Chicken Fillet 1kg/pack",
         listed_price="16.80", currency="MYR", pack_qty="1", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="1 day",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Klang Valley, Malaysia",
         source_url="https://www.supplybunny.com/en/products/halal-frozen-chicken-fillet-1kg-pack-sold-per-pack",
         available="no",
         notes="Page states 'Chicken Fillet Halal Certificate' and 'Next Day Delivery KL & Major Selangor Area, order cut-off 10pm'. WARNING shown on the page: 'Not currently available to order - this product's supplier is not active on SupplyBunny right now'. SupplyBunny's 2026 HORECA price guide states boneless breast RM12-RM16/kg and typical wholesale MOQ 50-200 kg per delivery (guide, not this listing)."),

    dict(material_name="Chicken filling", tier="full",
         supplier_name="FarmiHub",
         product_name="Wholesale chicken fillet / chicken parts",
         listed_price="", currency="MYR", pack_qty="", pack_unit="", comparable_basis="kg",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Malaysia",
         available="yes", material_match="yes",
         source_url="https://farmihub.com/poultry-wholesale/",
         notes="NO PRICE PUBLISHED - quotation by WhatsApp only, so no comparable price is recorded (scored as 'not comparable', not zero). Page states chicken fillet is an available part, blast-frozen, from 100% halal-certified sources. No MOQ or lead time published."),

    dict(material_name="Peanut butter", tier="full",
         supplier_name="Leeng Marketing (listed on Borong)",
         product_name="Lady's Choice Peanut Butter 3KG",
         listed_price="110.00", currency="MYR", pack_qty="3", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="3", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Wilayah Persekutuan, Malaysia",
         source_url="https://market.borong.com/v/leeng-marketing/product/Ladys-Choice-Peanut-Butter-3KG-Per-Unit/137806",
         notes="Branded (Lady's Choice) peanut butter, the only peanut butter found on Borong with a published price. Minimum order = the 3 kg unit as listed. RRP MYR 117.00. Allergen: peanut."),

    dict(material_name="Peanut butter", tier="full",
         supplier_name="Fresh Bulk",
         product_name="Fresh Bulk Classic Peanut Butter SMOOTH",
         listed_price="11.99", currency="MYR", pack_qty="", pack_unit="", comparable_basis="kg",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Malaysia",
         source_url="https://www.freshbulkonline.com/product/fresh-bulk-peanut-butter",
         notes="NO NET WEIGHT PUBLISHED on the page, so no per-kg price can be computed - left blank rather than assumed. States halal certified, no added sugar, no emulsifier. Sale price RM11.99 (was RM21.90)."),

    dict(material_name="Honey", tier="full",
         supplier_name="ETL Lab PLT (listed on Borong)",
         product_name="HONEY 3KG",
         listed_price="29.40", currency="MYR", pack_qty="3", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="3", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/etl-lab-plt/product/HONEY-3KG-3-KG-Per-Unit/146834",
         notes="Generic unbranded 'HONEY' listing at MYR 9.80/kg - far below pure honey market levels, which is exactly the adulteration risk noted in the tiering decision. No purity, origin or composition detail published. Verify composition before using in a product labelled as honey."),

    dict(material_name="Honey", tier="full",
         supplier_name="e-Petani (listed on Borong)",
         product_name="Deligold HONEY 1kg",
         listed_price="15.50", currency="MYR", pack_qty="1", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="1", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/e-petani/product/Deligold-HONEY-1kg-KLANG-VALLEY-ONLY/148611",
         notes="[KLANG VALLEY ONLY]. Deligold also sells 'Honey Syrup (Sirap Madu)' as a separate product, so confirm whether this SKU is honey or honey-flavoured syrup before use. RRP MYR 17.83."),

    dict(material_name="Honey", tier="full",
         supplier_name="Nores Marketing Sdn Bhd (listed on Borong)",
         product_name="LAMIS Natural Pure Honey (1kg bottle)",
         listed_price="94.50", currency="MYR", pack_qty="1", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="1", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Pulau Pinang, Malaysia",
         source_url="https://market.borong.com/v/nores-marketing-sdn-bhd/product/LAMIS-Natural-Pure-Honey1kg-bottle/145332",
         notes="Marketed as 'Natural Pure Honey'; the most expensive of the four at MYR 94.50/kg, consistent with the wide purity-driven price spread that put honey in the full tier. Same seller also lists 300 g (MYR 35.90) and 20 g x 15 sachets (MYR 26.50)."),

    dict(material_name="Honey", tier="full",
         supplier_name="Excel Big Bulk Trading Sdn Bhd (listed on Borong)",
         product_name="Honey 12 x 1kg",
         listed_price="98.30", currency="MYR", pack_qty="12", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="12", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/excel-big-bulk-trading-sdn-bhd/product/Honey-12-x-1kg/137645",
         notes="Cheapest per kg (MYR 8.19) of the four, but the listing publishes no brand, origin or purity detail. Same seller lists 'SO PURE HONEY SYRUP 1KG 12 X 1KG' at a similar price - confirm whether this SKU is honey or syrup. Minimum order = the 12 kg carton."),

    # --------------------------------------------------------------- LIGHT TIER
    dict(material_name="Flour", tier="light",
         supplier_name="PJ Grocer Sdn Bhd (listed on Borong)",
         product_name="Blue Key Flour 25KG",
         listed_price="78.50", currency="MYR", pack_qty="25", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="25", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/pj-grocer/product/Blue-Key-Flour-25KG-KLANG-VALLEY-ONLY/136962",
         notes="LIGHT RESEARCH. [KLANG VALLEY ONLY]. Cheapest of the three at MYR 3.14/kg. RRP MYR 85.60."),

    dict(material_name="Flour", tier="light",
         supplier_name="Borong Runcit (listed on Borong)",
         product_name="Blue Key Tepung Gandum 25kg",
         listed_price="82.80", currency="MYR", pack_qty="25", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="25", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Wilayah Persekutuan, Malaysia",
         source_url="https://market.borong.com/v/borong-runcit/product/Blue-Key-Tepung-Gandum-25kg/127613",
         notes="LIGHT RESEARCH. Same brand as the cheapest option but MYR 3.31/kg; no KLANG VALLEY restriction, so usable outside the Klang Valley. RRP MYR 108.00."),

    dict(material_name="Flour", tier="light",
         supplier_name="PJ Grocer Sdn Bhd (listed on Borong)",
         product_name="GOLD KEY Cake Flour 25kg",
         listed_price="104.00", currency="MYR", pack_qty="25", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="25", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/pj-grocer/product/GOLD-KEY-Cake-Flour-25kg-KLANG-VALLEY-ONLY/136848",
         notes="LIGHT RESEARCH. Cake flour is a lower-protein specification, not a like-for-like swap for general-purpose flour - recorded for reference, MYR 4.16/kg. [KLANG VALLEY ONLY]."),

    dict(material_name="Sugar", tier="light",
         supplier_name="Borong Runcit (listed on Borong)",
         product_name="CSR GULA KASAR 1KG x 12",
         listed_price="39.33", currency="MYR", pack_qty="12", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="12", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Wilayah Persekutuan, Malaysia",
         source_url="https://market.borong.com/v/borong-runcit/product/CSR-GULA-KASAR-1KG-x-12/127622",
         notes="LIGHT RESEARCH. Cheapest of the three at MYR 3.28/kg and the smallest carton (12 kg). RRP MYR 51.00."),

    dict(material_name="Sugar", tier="light",
         supplier_name="Borong Runcit (listed on Borong)",
         product_name="Gula Prai Super Premium 1kgx24",
         listed_price="96.00", currency="MYR", pack_qty="24", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="24", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Wilayah Persekutuan, Malaysia",
         source_url="https://market.borong.com/v/borong-runcit/product/Gula-Prai-Super-Premium-1kgx24/127852",
         notes="LIGHT RESEARCH. MYR 4.00/kg. RRP MYR 98.00."),

    dict(material_name="Sugar", tier="light",
         supplier_name="PJ Grocer Sdn Bhd (listed on Borong)",
         product_name="CSR Caster Sugar 50kg",
         listed_price="250.00", currency="MYR", pack_qty="50", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="50", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/pj-grocer/product/CSR-Caster-Sugar-50kg-KLANG-VALLEY-ONLY/136824",
         notes="LIGHT RESEARCH. Caster (finer) sugar at MYR 5.00/kg and a 50 kg minimum - the largest commitment of the three. [KLANG VALLEY ONLY]. RRP MYR 240.00 (below the selling price shown)."),

    dict(material_name="Tea bag", tier="light",
         supplier_name="HANKER FOODS (M) SDN BHD (listed on Borong)",
         product_name="Lipton Tea Yellow Label Individual Env (1.85g x 100's) x 12 BOX",
         listed_price="229.90", currency="MYR", pack_qty="1200", pack_unit="pcs", comparable_basis="100 pcs",
         minimum_order_qty="1200", minimum_order_unit="pcs", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/hanker-foods-m-sdn-bhd/product/Lipton-Tea-Yellow-Label-Individual-Env-A1200-1.85g-X-100s-X-12-BOX/135820",
         notes="LIGHT RESEARCH. 1,200 individually enveloped bags (12 boxes x 100). MYR 19.16 per 100 bags. RRP MYR 239.00."),

    dict(material_name="Tea bag", tier="light",
         supplier_name="YEE LEE TRADING CO. SDN BHD (listed on Borong)",
         product_name="144 x 25s Sabah Tea Bags",
         listed_price="592.50", currency="MYR", pack_qty="3600", pack_unit="pcs", comparable_basis="100 pcs",
         minimum_order_qty="3600", minimum_order_unit="pcs", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Wilayah Persekutuan, Malaysia",
         source_url="https://market.borong.com/v/yeelee/product/144-x-25s-Sabah-Tea-Bags/61314",
         notes="LIGHT RESEARCH. Cheapest per 100 bags (MYR 16.46) but the largest commitment: 3,600 bags. Malaysian Sabah tea. RRP MYR 675.36."),

    dict(material_name="Tea bag", tier="light",
         supplier_name="BREW LAB RESOURCES SDN BHD (listed on Borong)",
         product_name="JAF TEA English Breakfast 100's box",
         listed_price="41.00", currency="MYR", pack_qty="100", pack_unit="pcs", comparable_basis="100 pcs",
         minimum_order_qty="100", minimum_order_unit="pcs", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Melaka, Malaysia",
         source_url="https://market.borong.com/v/brew-lab-resources-sdn-bhd/product/JAF-TEA-English-Breakfast-100s-box/121070",
         notes="LIGHT RESEARCH. Most expensive per 100 bags (MYR 41.00) but the smallest commitment (one 100-bag box) - relevant while P002 volume is uncertain. RRP MYR 42.00."),

    dict(material_name="Lemon syrup", tier="light",
         supplier_name="Happy Popper",
         product_name="B&B Concentrated Fruit Syrup Lemon 5kg (BT-SY127)",
         listed_price="49.00", currency="MYR", pack_qty="5", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="5", minimum_order_unit="kg", delivery_or_lead_time="",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://www.happypopper.net/index.php?route=product/product&product_id=1777",
         notes="LIGHT RESEARCH. BASIS NOTE: sold by weight (5 kg), so the comparable price is per kg, not per litre; materials.csv records lemon syrup in ml, so the two are not directly reconciled here. Tiered price: RM49.00, RM47.50, RM46.50 for 4+. Free shipping to Selangor at MYR 150+; MYR 20 flat below. No delivery-day promise published - left blank."),

    dict(material_name="Plastic cup 500ml", tier="light",
         supplier_name="Panagawa Sdn Bhd",
         product_name="500ml PP Cup AO500 (carton 20 x 100 pcs)",
         listed_price="", currency="MYR", pack_qty="2000", pack_unit="pcs", comparable_basis="100 pcs",
         minimum_order_qty="2000", minimum_order_unit="pcs", delivery_or_lead_time="",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Johor Bahru, Malaysia",
         source_url="https://www.panagawa.com/showproducts/productid/6704503/500ml-pp-cup-ao500/",
         notes="LIGHT RESEARCH. NO PRICE PUBLISHED - enquiry-based, so no comparable price is recorded. Specs stated: 500 ml / 16.5 oz polypropylene, transparent, packing 20 x 100 pcs = 2,000 per carton, gross weight 13 kg. No delivery time published."),

    dict(material_name="Paper cookie bag", tier="light",
         supplier_name="Akah Marketing",
         product_name="Bakery Paper Bag / Pastry Bag",
         listed_price="", currency="MYR", pack_qty="", pack_unit="", comparable_basis="100 pcs",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Malaysia",
         source_url="https://www.akahmarketing.com/ourproducts/cid/650024/cat/paper-bag-food-packaging-bag-bakery-paper-bag-pastry-bag/",
         notes="LIGHT RESEARCH. NO PRICE PUBLISHED - packaging is quoted per job (size, print, quantity), so no comparable price is recorded rather than estimated. Malaysian packaging specialist carrying bakery/pastry paper bags."),

    dict(material_name="Paper cookie bag", tier="light",
         supplier_name="Xin Packs",
         product_name="Paper bag food packaging (custom kraft / window bags)",
         listed_price="", currency="MYR", pack_qty="", pack_unit="", comparable_basis="100 pcs",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Malaysia",
         source_url="https://xinpacks.com/paper-bag-food-packaging",
         notes="LIGHT RESEARCH. NO PRICE PUBLISHED - quote on request. Malaysian packaging supplier for kraft/handle/window bags. Custom print means price depends on artwork and quantity."),

    dict(material_name="Banana", tier="light",
         supplier_name="SupplyBunny (Fresh Veg Fruits supplier)",
         product_name="Banana Cavendish/Pisang Montel 1KG+-/PKT",
         listed_price="6.25", currency="MYR", pack_qty="1", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="1", minimum_order_unit="kg", delivery_or_lead_time="",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Klang Valley, Malaysia",
         source_url="https://www.supplybunny.com/en/products/banana-cavendish-pisang-montel-1kg-pkt",
         notes="LIGHT RESEARCH. BASIS NOTE: the source sells bananas by weight (MYR 6.25/kg) while materials.csv counts 1 banana per muffin, so the two units are not reconciled here - the number of bananas per kg is NOT stated by the source and is not assumed. No delivery time published on the listing."),

    dict(material_name="Muffin cup", tier="light",
         supplier_name="Peng Kee Enterprise Sdn Bhd",
         product_name="PET 5050 Laminated Cup (Muffin Cup) 100's x 60 pkt",
         listed_price="", currency="MYR", pack_qty="100", pack_unit="pcs", comparable_basis="100 pcs",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Pulau Pinang, Malaysia",
         source_url="https://pengkeeonline.com/baking-cup",
         notes="LIGHT RESEARCH. NO PRICE PUBLISHED on the category page - prices require login/WhatsApp enquiry, so no comparable price is recorded. Packing stated as +/- 100's per pkt, 60 pkt per carton. Same seller lists 1,000's cup cake cases and 200's baking cases."),

    dict(material_name="Spice mix", tier="light",
         supplier_name="Borong Runcit (listed on Borong)",
         product_name="BABAS MEAT CURRY POWDER 1KG",
         listed_price="26.80", currency="MYR", pack_qty="1", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="1", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Wilayah Persekutuan, Malaysia",
         source_url="https://market.borong.com/v/borong-runcit/product/BABAS-MEAT-CURRY-POWDER-1KG/127729",
         notes="LIGHT RESEARCH. Blended spice powder (the closest published match to a generic 'spice mix'). Cheapest of the three at MYR 26.80/kg, 1 kg minimum. RRP MYR 33.00."),

    dict(material_name="Spice mix", tier="light",
         supplier_name="ABBY'S HEALTHY (listed on Borong)",
         product_name="SERBUK BERIANI 100G",
         listed_price="3.50", currency="MYR", pack_qty="100", pack_unit="g", comparable_basis="kg",
         minimum_order_qty="100", minimum_order_unit="g", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Melaka, Malaysia",
         source_url="https://market.borong.com/v/abbys-healthy/product/SERBUK-BERIANI-100G/144961",
         notes="LIGHT RESEARCH. MYR 35.00/kg. Smallest pack (100 g), so the lowest cash outlay even though the per-kg price is higher. RRP MYR 3.85."),

    dict(material_name="Spice mix", tier="light",
         supplier_name="Heritage Food Network (listed on Borong)",
         product_name="CAJUN SPICE 500gm",
         listed_price="24.50", currency="MYR", pack_qty="500", pack_unit="g", comparable_basis="kg",
         minimum_order_qty="500", minimum_order_unit="g", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/heritage-food-network/product/CAJUN-SPICE-500gm-unit/136360",
         notes="LIGHT RESEARCH. Most expensive per kg (MYR 49.00) - a Western Cajun blend, recorded for reference rather than as the default choice for a Malaysian bun filling. RRP MYR 27.00."),

    dict(material_name="Wax paper", tier="light",
         supplier_name="Image Magic",
         product_name="Greaseproof wrapping sheets 300x300mm (100 sheets)",
         listed_price="50.00", currency="MYR", pack_qty="100", pack_unit="pcs", comparable_basis="100 pcs",
         minimum_order_qty="100", minimum_order_unit="pcs", delivery_or_lead_time="2 days",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Malaysia",
         source_url="https://imagemagic.com.my/food-grade-wrapping-paper/",
         notes="LIGHT RESEARCH. MYR 50.00 for 100 sheets (MYR 0.50 each); production approx 2 working days, delivery extra. FOOD-SAFETY WARNING stated by the supplier itself: the printed sheet is NOT certified for direct food contact and must not be used to wrap hot or oily food - P004 wraps a chicken bun, so this SKU is recorded for price reference only and needs an inner food-safe barrier."),

    dict(material_name="Wax paper", tier="light",
         supplier_name="Magnus Oriental",
         product_name="Greaseproof Liners & Sheets GREA-01 (12x12in, 500/ream)",
         listed_price="", currency="MYR", pack_qty="500", pack_unit="pcs", comparable_basis="100 pcs",
         minimum_order_qty="5000", minimum_order_unit="pcs", delivery_or_lead_time="1-3 days",
         seller_type="official_shop", listing_updated_within_90d="not stated",
         location="Malaysia",
         source_url="https://magnusoriental.com.my/products/bags-wraps-takeaway-packaging/greaseproof-liners",
         notes="LIGHT RESEARCH. NO PRICE PUBLISHED - pricing scales with volume, so no comparable price is recorded. Stated as food-contact safe (unlike the Image Magic option). Stock items ship 1-3 working days across Malaysia; custom print MOQ 5,000; packing 500 per ream, 10 reams per case."),

    dict(material_name="Rolled oats", tier="light",
         supplier_name="PepsiCo Foods Malaysia (listed on Borong)",
         product_name="QUAKER WHOLE ROLLED OATS 800G x 12",
         listed_price="125.96", currency="MYR", pack_qty="9.6", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="9.6", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/pepsi-co/product/QUAKER-WHOLE-ROLLED-OATS-800G-x-12/135742",
         notes="LIGHT RESEARCH. Cheapest of the three at MYR 13.12/kg (12 x 800 g = 9.6 kg carton). Branded whole rolled oats, the exact spec used by P005. RRP MYR 128.40."),

    dict(material_name="Rolled oats", tier="light",
         supplier_name="SCC MARKETPLACE (listed on Borong)",
         product_name="CED Organic Rolled Oat (450g x 24)",
         listed_price="182.40", currency="MYR", pack_qty="10.8", pack_unit="kg", comparable_basis="kg",
         minimum_order_qty="10.8", minimum_order_unit="kg", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/scc-marketplace/product/CED-Organic-Rolled-Oat-450gx24/135888",
         notes="LIGHT RESEARCH. Organic rolled oats at MYR 16.89/kg (24 x 450 g = 10.8 kg carton). RRP MYR 228.00."),

    dict(material_name="Rolled oats", tier="light",
         supplier_name="Wide Tropism Marketing Sdn Bhd (listed on Borong)",
         product_name="Organic Regular Rolled Oat 400g",
         listed_price="8.00", currency="MYR", pack_qty="400", pack_unit="g", comparable_basis="kg",
         minimum_order_qty="400", minimum_order_unit="g", delivery_or_lead_time="3-5 days",
         seller_type="marketplace_listed_supplier", listing_updated_within_90d="not stated",
         location="Selangor, Malaysia",
         source_url="https://market.borong.com/v/Wide-Tropism-Marketing/product/Organic-Regular-Rolled-Oat-400g/141120",
         notes="LIGHT RESEARCH. Most expensive per kg (MYR 20.00) but the smallest pack (400 g), so the lowest cash commitment - relevant because P005 sold only 6 units in the period. RRP MYR 8.90."),

    dict(material_name="Granola bar wrapper", tier="light",
         supplier_name="None found in light research",
         product_name="Granola bar wrapper (no Malaysian supplier with a published price)",
         listed_price="", currency="MYR", pack_qty="", pack_unit="", comparable_basis="100 pcs",
         minimum_order_qty="", minimum_order_unit="", delivery_or_lead_time="",
         seller_type="", listing_updated_within_90d="not stated",
         location="",
         source_url="https://www.alibaba.com/showroom/granola-bar-wrapper_5.html",
         notes="LIGHT RESEARCH FOUND NO USABLE SOURCE. The only listings found are overseas marketplaces (Alibaba/AliExpress) with no published MYR price and no Malaysian seller, so nothing is recorded rather than inventing a number. This material cannot be scored until a quotation is obtained - the run reports it as an open gap."),
]


def dec(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def to_basis(qty: Decimal, unit: str, basis: str):
    """Convert a stated pack quantity into the comparison basis. Returns None if not convertible."""
    if qty is None or qty <= 0:
        return None
    u = (unit or "").strip().lower()
    # normalise the stated pack unit into the basis family
    if basis == "kg":
        if u in ("kg", "kilogram", "kilograms"):
            return qty
        if u in ("g", "gram", "grams"):
            return qty / Decimal(1000)
        return None
    if basis == "litre":
        if u in ("l", "litre", "litres", "liter", "liters"):
            return qty
        if u in ("ml", "millilitre", "millilitres"):
            return qty / Decimal(1000)
        return None
    if basis == "100 pcs":
        if u in ("pcs", "piece", "pieces", "unit", "units", "sheet", "sheets"):
            return qty / Decimal(100)
        return None
    return None


def build() -> list[dict]:
    out = []
    for r in ROWS:
        row = {c: r.get(c, "") for c in RAW_COLUMNS}
        row["retrieved_at"] = RETRIEVED_AT

        price = dec(r.get("listed_price"))
        basis = r.get("comparable_basis", "")
        packs = to_basis(dec(r.get("pack_qty")), r.get("pack_unit", ""), basis)

        if price is None or packs is None or packs == 0:
            comparable = ""          # not stated / not convertible -> scored as "not comparable"
        else:
            comparable = f"{(price / packs).quantize(Decimal('0.0001')):.4f}"

        moq_qty = dec(r.get("minimum_order_qty"))
        moq_unit = (r.get("minimum_order_unit") or "").strip()
        minimum_order = f"{moq_qty.normalize()} {moq_unit}".strip() if (moq_qty and moq_unit) else ""

        row["comparable_price"] = comparable
        row["price_unit"] = (f"{r.get('pack_qty','')} {r.get('pack_unit','')}".strip()
                             if r.get("pack_qty") else "not stated")
        row["minimum_order"] = minimum_order
        row["comparable_basis"] = basis
        out.append(row)
    return out


def main() -> int:
    rows = build()

    RAW.parent.mkdir(parents=True, exist_ok=True)
    with RAW.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RAW_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in RAW_COLUMNS})

    # Columns the scoring engine expects (RESEARCH_COLUMNS in app/bizflow_supplier.py)
    sys.path.insert(0, str(ROOT / "app"))
    from bizflow_supplier import RESEARCH_COLUMNS  # noqa: E402

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESEARCH_COLUMNS, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r.setdefault("score", "")
            r.setdefault("score_breakdown", "")
            r.setdefault("rank", "")
            r.setdefault("recommended", "")
            r.setdefault("available", "")
            r.setdefault("material_match", "")
            w.writerow({c: r.get(c, "") for c in RESEARCH_COLUMNS})

    priced = [r for r in rows if r["comparable_price"]]
    mats = sorted({r["material_name"] for r in rows})
    mats_priced = sorted({r["material_name"] for r in priced})
    print(f"raw rows written      : {len(rows)}  -> {RAW.relative_to(ROOT)}")
    print(f"input rows written    : {len(rows)}  -> {OUT.relative_to(ROOT)}")
    print(f"rows with a comparable price : {len(priced)}")
    print(f"materials covered     : {len(mats)}")
    print(f"materials with >=1 comparable price : {len(mats_priced)}")
    gap = [m for m in mats if m not in mats_priced]
    if gap:
        print("materials with NO comparable price (open gap): " + ", ".join(gap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
