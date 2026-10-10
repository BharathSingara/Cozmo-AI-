# Pricing and Valuation Methodology — Library Contents Claim Agent

## 1. Valuation Philosophy & Integrity Rules

Insurance claim packets must withstand forensic scrutiny by claims adjusters, legal counsel, and underwriters. Consequently, the valuation engine is built upon five non-negotiable principles:

1. **No LLM Price Hallucinations:** Large language models frequently invent believable prices from parametric memory. The system completely prohibits AI-generated price numbers.
2. **Every Valuation Must Have an HTTPS Source:** An amount is only valid if linked to a live, retrievable merchant or marketplace product listing URL with a UTC retrieval timestamp.
3. **No Digital Product Substitutions:** An eBook or Kindle listing (e.g., $9.99) cannot serve as the replacement cost for a hardcover or paperback volume ($28.00).
4. **Separation of New Replacement Cost and Used Market Value:** New retail replacement cost is evaluated separately from pre-owned used listings.
5. **Missing Prices Remain Null:** If no verifiable listing exists, the amount is stored as `null`. It is omitted from financial sums and incremented in `unpriced_books`.

---

## 2. Price Sourcing Architecture

```
Bibliographic Work (Title, Author, ISBN)
         │
         ▼
Market Search (Country Code, Local Currency)
         │
   ┌─────┴────────────────────────┐
   ▼                              ▼
SerpApi Google Shopping       eBay Browse API
(Regional Merchants)          (Used / Secondary Market)
   │                              │
   └──────────────┬───────────────┘
                  │
                  ▼
         Negative Filter Pipeline:
         - Exclude "ebook", "kindle", "audiobook"
         - Exclude "summary of", "study guide for"
         - Exclude non-matching currency
                  │
                  ▼
         Condition Separation:
         - NEW / BRAND_NEW  ──► Replacement Cost (Price)
         - USED / PRE_OWNED ──► Used Market Value (Price)
                  │
                  ▼
         Appraisal Threshold Guard:
         - Amount >= Threshold (e.g., 80,000 INR / $1,000 USD)?
           ├── YES: Flag status="needs_appraisal" & Exclude from Totals
           └── NO:  Admit to Deterministic Totals
```

---

## 3. Supported Listing Providers

### 3.1 Google Shopping via SerpApi (Preferred for India & Multilateral Markets)
- **Engine:** `google_shopping`
- **Parameters:** `gl` (country code: `in`, `us`, `gb`, `ca`, `au`, `de`, `fr`), `hl=en`, query restricted to title and author.
- **Retailer Retention:** Captures the merchant name (e.g., "Amazon India", "Crossword", "Barnes & Noble") and direct product link.
- **Condition Parsing:** Listings marked with `second_hand_condition` are categorized as Used; unmarked retail listings are categorized as New.

### 3.2 eBay Browse API (Secondary / Rare Physical Market)
- **Endpoint:** `https://api.ebay.com/buy/browse/v1/item_summary/search`
- **Marketplace Headers:** `EBAY_US`, `EBAY_GB`, `EBAY_CA`, `EBAY_AU`, `EBAY_DE`, `EBAY_FR`.
- **Condition Mapping:**
  - *New:* `NEW`, `BRAND_NEW`.
  - *Used:* `LIKE_NEW`, `VERY_GOOD`, `GOOD`, `ACCEPTABLE`, `PRE_OWNED`.

---

## 4. Appraisal Thresholds & High-Value Items

Physical libraries frequently contain first editions, signed copies, out-of-print historical texts, or original artworks. Applying ordinary retail replacement prices to these items introduces severe underwriting risk.

### Configurable Currency Thresholds
The system maintains per-currency thresholds (defined in `.env`):
- `APPRAISAL_THRESHOLD_INR = 80,000`
- `APPRAISAL_THRESHOLD_USD = 1,000`
- `APPRAISAL_THRESHOLD_GBP = 800`
- `APPRAISAL_THRESHOLD_EUR = 900`
- `APPRAISAL_THRESHOLD_CAD = 1,400`
- `APPRAISAL_THRESHOLD_AUD = 1,600`

### Safeguard Enforcement
If any sourced listing price meets or exceeds the threshold:
1. The book is flagged with `status: "needs_appraisal"`.
2. A warning is appended to `book.notes`: `"Price exceeds <threshold> <currency> appraisal threshold; listing indicative only"`.
3. The item is routed to the human review queue.
4. **Crucially: The item's monetary valuation is excluded from automatic claim totals** until an independent certified appraiser verifies its authenticity and condition.

---

## 5. Non-Book Belongings Valuation

For furniture, electronics, and room contents:
1. The system searches for the verified brand and model (e.g., "Herman Miller Aeron Chair").
2. Comparable merchant listings are queried to establish a replacement price range (`low` and `high`).
3. If brand and model are unverified from the video, the valuation is recorded as unavailable (`low: null, high: null`) with reason: `"Brand or model not verified; broad catalogue prices not comparable"`.
4. Artwork is automatically assigned `status: "needs_appraisal"` and excluded from automated totals.
