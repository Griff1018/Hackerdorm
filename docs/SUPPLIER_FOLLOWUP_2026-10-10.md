# Sprint 2.1 supplier follow-up — 2026-10-10

Two short checks were requested before Sprint 3.

## Chicken filling

- **Exact, available match found, but no comparable price:** FarmiHub's Malaysian poultry page explicitly lists **Chicken Fillet Available**, describes frozen cuts from halal-certified sources, and provides an enquiry/quotation path. It does not publish a price, pack size, MOQ, or lead time. Result: record as an exact available source, but keep **no eligible priced supplier — needs quotation**. Source: https://farmihub.com/poultry-wholesale/ (retrieved 2026-10-10).
- **Not eligible:** KHL Frozen Food lists Chicken Fillet TH at RM14.00 wholesale with 2 kg x 6 packet carton packaging, but the page marks it **Pre Order**. It is therefore not currently available for an immediate PO. Source: https://khlfrozenfood.com/products/ (retrieved 2026-10-10).
- **Decision:** do not create a Chicken filling PO. The current engine reports no available eligible priced supplier; the FarmiHub quotation is the next safe action.

## Butter

- A short search for an exact **pure dairy butter** listing with a Malaysian supplier, current availability, published price, and stated pack size did not produce a verifiable match. Search results were comparison pages or did not establish that a listing was pure dairy butter. Existing Butter rows are spreads, buttery substitutes, or bake-stable flavouring products and remain excluded from recommendation.
- **Decision:** keep **no eligible supplier found — needs quotation**. Do not convert a spread or substitute into Butter.

## Safety rule

Price alone is insufficient. A listing must be (1) available/active, (2) the specified material, and (3) price-comparable before it can be recommended or used in a draft PO.
