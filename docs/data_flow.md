# Data Flow & Lifecycle Specification — Library Contents Claim Agent

## 1. Overview

This document specifies the exact movement, transformation, and validation of data through the Library Contents Claim Agent across its entire lifecycle—from the initial optical capture of bookshelf photons to the generation of the final canonical JSON claim packet and PDF report.

---

## 2. End-to-End Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as Policyholder / Adjuster
    participant Browser as Browser Client (HTML5 / WebRTC / Web Speech)
    participant Gateway as FastAPI Gateway (api.py)
    participant Vision as Perception Pipeline (vision.py / tracker.py)
    participant Store as State & Evidence Store (store.py)
    participant Worker as Background Task (pipeline.py)
    participant Catalog as Bibliographic Service (catalog.py / Open Library)
    participant Pricing as Market Pricing (pricing.py / Google Shopping / eBay)
    participant Report as Reporting Engine (reporting.py / ReportLab)

    User->>Browser: Select Country (IN) & Currency (INR), Click "Start sweep"
    Browser->>Gateway: POST /api/sessions {country: "IN", currency: "INR"}
    Gateway->>Store: Initialize Packet & create data/sessions/<sid>/
    Store-->>Gateway: Session Created
    Gateway-->>Browser: 201 Created {id: "<sid>", packet: {...}}
    Browser->>User: Spoken Greeting ("Welcome. Market confirmed: IN, INR...")

    loop Continuous Sweep (~Every 2.3 seconds)
        Browser->>Browser: Capture Canvas JPEG (max 1100px, 78% quality)
        Browser->>Gateway: POST /api/sessions/<sid>/frames?shelf=Shelf A (image/jpeg)
        Gateway->>Vision: decode_image(raw) & quality(image)
        Vision-->>Gateway: Quality scores (blur, glare, under-exposure)
        Gateway->>Store: Write frames/<uuid>.jpg
        
        alt Quality Unusable (Blur < 35 or Glare > 0.35)
            Gateway-->>Browser: Warning emitted ("Motion blur..."), Frame preserved
        else Quality Usable
            Gateway->>Vision: Detect candidates (Gemini VLM or local Canny dual-morphology)
            Vision-->>Gateway: Raw bounding boxes [ymin, xmin, ymax, xmax]
            Gateway->>Vision: Estimate homography (ORB + RANSAC) with previous frame
            Vision-->>Gateway: Matched pairs & new instance proposals
            Gateway->>Store: Update session packet with new Book / Item instances
            Gateway-->>Browser: 200 OK {packet, new_books: N, new_items: M}
            Browser->>User: Update live counts (e.g., "12 saved")
            
            opt New Book Candidates Exist
                Gateway->>Worker: Spawn background task enrich(sid, new_books, new_items)
                Worker->>Vision: Crop spine image & CLAHE contrast enhancement
                Worker->>Vision: Multi-PSM Tesseract OCR (--psm 6, --psm 11, --psm 3)
                Worker->>Catalog: identify_book(ocr_text, title_hint)
                Catalog-->>Worker: Canonical Work Title, Author, Open Library URL
                Worker->>Pricing: book_prices(title, author, isbn, country, currency)
                Pricing-->>Worker: New replacement price & Used market listing with source URL
                Worker->>Store: Lock session & atomic update Book records
            end
        end
    end

    opt Operator Voice / UI Correction During Sweep
        User->>Browser: Verbal Command ("Title is The Great Gatsby" or "Skip shelf")
        Browser->>Gateway: POST /api/sessions/<sid>/corrections {command, ref_id, value}
        Gateway->>Store: Record in append-only audit_log & mutate active record
        opt Title Correction
            Gateway->>Worker: Spawn recheck_book(sid, ref_id, value)
            Worker->>Catalog: Re-verify corrected title against Open Library
            Worker->>Pricing: Re-query market listings for corrected title
            Worker->>Store: Update book status, prices, and totals
        end
        Gateway-->>Browser: Updated Packet
    end

    opt Operator Room Dimension Confirmation
        User->>Browser: Input Room Length, Width, Height, Shape
        Browser->>Gateway: POST /api/sessions/<sid>/room {length_m: 4, width_m: 3, height_m: 2.5, shape: "rectangular"}
        Gateway->>Store: Calculate floor area (12 m²) and wall area (35 m²) deterministically
        Gateway-->>Browser: Updated Room Schema
    end

    User->>Browser: Click "Finish & build claim"
    Browser->>Gateway: POST /api/sessions/<sid>/finish
    Gateway->>Worker: Await pending enrichment tasks (up to 240s timeout)
    Gateway->>Store: Validate all evidence frame refs exist on disk
    Gateway->>Store: Compute final deterministic totals & review queue
    Gateway->>Report: write_claim(packet) -> claim_packet.json, claim_report.html, claim_report.pdf
    Gateway-->>Browser: 200 OK {packet, report: "...", pdf_report: "...", download: "..."}
    Browser->>User: Spoken notification ("Claim packet ready. 62 detected books...")
    User->>Browser: Download JSON / HTML / PDF / Evidence ZIP
```

---

## 3. Data Schema Transformations by Stage

### Stage 1: Frame Ingestion & Quality Control
- **Input:** Raw binary byte stream (`image/jpeg`, max 4MB).
- **Transformation:**
  - NumPy array decode: `cv2.imdecode(arr, cv2.IMREAD_COLOR)`
  - Aspect downsampling if width/height exceeds 2200px.
  - Laplacian variance: $\text{Var}(\nabla^2 I)$
  - Saturated glare fraction: $\frac{\sum (R > 245 \land G > 245 \land B > 245)}{W \times H}$
  - Dark pixel fraction: $\frac{\sum (I_{\text{gray}} < 25)}{W \times H}$
- **Output:** Frame artifact on disk `data/sessions/<sid>/frames/<uuid>.jpg` and Quality Dict:
  ```json
  {
    "blur_score": 112.45,
    "glare_fraction": 0.021,
    "dark_fraction": 0.045,
    "warnings": [],
    "usable": true
  }
  ```

### Stage 2: Geometric Tracking & Deduplication
- **Input:** Bounding boxes $[y_1, x_1, y_2, x_2]$ in current frame, previous frame keypoints/descriptors.
- **Transformation:**
  - Keypoint matching: ORB detector (1000 features) + BruteForce Hamming distance with Lowe's ratio test ($d_1 < 0.72 \cdot d_2$).
  - Homography estimation: $H \in \mathbb{R}^{3 \times 3}$ using RANSAC (threshold 4.0px).
  - Perspective transformation: $\mathbf{x}' = H \mathbf{x}$.
  - Spatial overlap: Intersection-over-Union ($\text{IoU} > 0.36$) matching one-to-one.
- **Output:**
  - Matched existing items: Frame reference appended to `evidence_refs`.
  - Unmatched new items: Instantiated with UUIDs (`book_<hex>` or `item_<hex>`).

### Stage 3: Spine OCR & Catalogue Verification
- **Input:** Bounding box crop from native frame.
- **Transformation:**
  - CLAHE contrast enhancement: Clip limit 2.0, tile grid $8 \times 8$.
  - Multi-rotation variants: $0^\circ, 90^\circ, 270^\circ$.
  - Tesseract OCR across PSM 6 (uniform block), PSM 11 (sparse text), PSM 3 (auto).
  - Subtitle stripping and normalization: Regex strip non-alphanumeric, split at `:`, `-`.
  - SequenceMatcher title similarity:
    $$\text{score} = \max(\text{sim}(\text{title}_{\text{full}}, q), \text{sim}(\text{title}_{\text{base}}, q))$$
- **Output:** Verified Book metadata:
  ```json
  {
    "title": "The Great Gatsby",
    "author": "F. Scott Fitzgerald",
    "id_confidence": 0.94,
    "status": "identified",
    "notes": ["Verified work: https://openlibrary.org/works/OL468523W"]
  }
  ```

### Stage 4: Physical Marketplace Price Sourcing
- **Input:** Verified Work Title, Author, Target Country, Target Currency.
- **Transformation:**
  - SerpApi Google Shopping / eBay Browse query.
  - Negative title filters: Exclude `"ebook"`, `"kindle"`, `"audiobook"`, `"summary of"`.
  - Condition classification: New retail vs. Used / Pre-owned.
  - Currency symbol validation: Recognizes regional symbols (`₹`, `$`, `£`, `€`) and ISO codes.
  - Valuation confidence calculation.
- **Output:** Price models with traceable HTTPS links:
  ```json
  {
    "replacement_cost": {
      "amount": 299.00,
      "currency": "INR",
      "source": "Amazon India (Google Shopping via SerpApi)",
      "url": "https://www.amazon.in/dp/...",
      "retrieved_at": "2026-10-09T16:20:00Z",
      "condition_assumed": "New or equivalent",
      "match_confidence": 0.70
    }
  }
  ```

### Stage 5: Deterministic Financial Aggregation
- **Input:** Active (non-excluded, non-appraisal) items.
- **Transformation:** Pure Python deterministic arithmetic.
  $$\text{books\_replacement\_cost} = \sum_{b \in B_{\text{active}}, \text{status} \ne \text{needs\_appraisal}} b.\text{replacement\_cost}.\text{amount}$$
  $$\text{books\_used\_value} = \sum_{b \in B_{\text{active}}, \text{status} \ne \text{needs\_appraisal}} b.\text{used\_value}.\text{amount}$$
- **Output:** Canonical `Totals` model in `claim_packet.json`.

---

## 4. State Persistence & Crash Resilience

All session modifications follow an atomic write-replace protocol:
1. Session state is serialized to `state.tmp` via Pydantic: `packet.model_dump_json(indent=2)`.
2. `state.tmp` is flushed and replaced atomically: `tmp.replace(folder / 'state.json')`.
3. In-flight enrichment tasks write per-item updates inside a session-keyed asynchronous re-entrant lock (`asyncio.Lock`), ensuring thread-safe concurrency without database deadlocks.
