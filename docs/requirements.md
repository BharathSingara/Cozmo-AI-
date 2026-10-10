# Requirements Specification — Library Contents Claim Agent

## 1. Executive Summary & Business Problem

When a catastrophic event occurs (e.g., water pipe burst, fire, smoke damage, theft) in a residence housing a significant personal library, documenting the loss is traditionally an error-prone, weeks-long ordeal. Claims adjusters and policyholders often resort to guessing titles, estimating lump-sum valuations, or manually photographing and typing thousands of book details.

The **Library Contents Claim Agent** solves this business problem by providing a browser-based, evidence-first room inventory application. The policyholder or claims adjuster conducts a single continuous video sweep across bookshelves, room furniture, walls, and corners. The application continuously ingests sampled frames, guides the user via spoken voice prompts, detects book spines and non-book belongings, verifies literary works against bibliographic catalogues, queries live physical marketplace listings for replacement and used values, calculates room floor and wall areas, flags items requiring expert human appraisal, and outputs a canonical, auditable claim packet in JSON, HTML, and PDF formats along with cryptographic provenance referencing raw image frames.

### Target Users
1. **Policyholder (Insured):** Conducts a guided self-inventory of their damaged or pre-loss library using a smartphone or tablet browser without requiring specialized app-store installations.
2. **Field Claims Adjuster:** Conducts on-site professional inspections, issues verbal corrections during sweeps, and exports audit-ready claim documentation.
3. **Desk Adjuster & Underwriter:** Reviews the final claim packet, scrutinizes the human review queue, validates market evidence links, and approves loss payouts based on deterministic financial totals.

---

## 2. Complete Functional Requirements

### 2.1 Live Camera Capture & Session Management
- **FR-01: Session Lifecycle:** Users must configure market country (e.g., `IN`, `US`, `GB`, `CA`, `AU`, `DE`, `FR`) and currency (`INR`, `USD`, `GBP`, `CAD`, `AUD`, `EUR`) prior to sweep initiation. The backend generates an unpredictable UUIDv4 session identifier.
- **FR-02: Live Frame Ingestion:** The browser captures real-time video via `navigator.mediaDevices.getUserMedia` and samples frames every ~2.3 seconds, transmitting JPEG binary payloads to `/api/sessions/{sid}/frames`.
- **FR-03: Real-Time Non-Blocking Capture:** Camera preview and frame transmission must continue unimpeded even while asynchronous backend enrichment runs.
- **FR-04: Session Completion & Locking:** Upon sweep conclusion (`POST /api/sessions/{sid}/finish`), the session is sealed, recording sweep duration, timestamp, and locking against further frame additions.

### 2.2 Voice Interaction & Audio Guidance
- **FR-05: Spoken Guidance:** Uses the browser `SpeechSynthesis` API to announce sweep start, provide movement pacing recommendations ("Walk slowly across all bookshelves"), alert users to capture warnings, and report completion statistics.
- **FR-06: Voice Commands & Transcription:** Integrates `SpeechRecognition` / `webkitSpeechRecognition` to interpret user commands during the live sweep:
  - `"skip that shelf"` -> Exclude entire shelf from monetary totals.
  - `"first edition"` / `"rare edition"` -> Flag most recently detected book for expert appraisal.
  - `"that painting is a print"` -> Reclassify artwork as commercial print.
  - `"you missed the bottom shelf"` / `"missed shelf"` -> Record warning to revisit missed areas within the same sweep.
  - `"next shelf"` -> Increment shelf identifier.
  - `"title is [Title]"` -> Correct unreadable title and trigger re-verification.
  - `"exclude book"` -> Exclude specific item from totals.
- **FR-07: Typed Correction Fallback:** A text command form and individual record action buttons are always accessible if voice transcription is unavailable.

### 2.3 Frame Quality Assessment
- **FR-08: Blur Detection:** Computes Laplacian variance on grayscale frames. Scores below 85 generate motion blur warnings advising the user to slow down. Frames below 35 are flagged as unusable for detection but preserved as evidence.
- **FR-09: Glare & Specular Reflection Detection:** Measures percentage of saturated pixels (>245). Values exceeding 9% prompt user to tilt the camera away from direct lighting.
- **FR-10: Low Light Warning:** Detects dark-pixel fractions (>35% below value 25) and advises illuminating the shelf.

### 2.4 Book Detection, OCR, and Bibliographic Identification
- **FR-11: Multi-Orientation Spine Detection:** Detects individual upright book spines (`aspect >= 1.4`) and flat/stacked horizontal books (`aspect >= 1.4` on horizontal axis) using contour edge analysis offline, or Gemini VLM proposals when enabled.
- **FR-12: Multi-Frame Tracking & Deduplication:** Tracks books across adjacent overlapping frames using ORB feature extraction, RANSAC homography estimation, and bipartite one-to-one bounding box matching to prevent double-counting during camera pan.
- **FR-13: Spine OCR:** Preprocesses cropped spine images with CLAHE contrast enhancement and runs Tesseract across multiple Page Segmentation Modes (`--psm 6`, `--psm 11`, `--psm 3`) and rotation angles (0°, 90°, 270°).
- **FR-14: Bibliographic Work Verification:** Verifies extracted title text against Open Library Search API. Subtitle variations are normalized. Returns verified work title, primary author, and Open Library work URL.
- **FR-15: Strict Anti-Hallucination Policy:** Books with illegible spines or unverified titles remain `status: "unidentified"` with `title: null`. Titles are never guessed from book color or generic AI completions.

### 2.5 Physical Sizing & Metric Measurements
- **FR-16: Established Coplanar Reference Requirement:** Physical dimensions (spine height and thickness in cm) are calculated strictly when an explicit coplanar reference (known length in cm and image pixel span) is provided for that shelf plane.
- **FR-17: Perspective & Depth Uncertainty:** Without a calibrated reference, dimensions remain `null` and are routed to the human review queue. Calculated dimensions record method and uncertainty bounds.
- **FR-18: Shelf Run Calculation:** Sums spine thicknesses across all active books on a shelf only if every book on that shelf has a verified metric thickness. If any book lacks thickness, total shelf run remains `null`.

### 2.6 Pricing, Valuation & Market Provenance
- **FR-19: Real Traceable Price Sources:** Fetches live physical marketplace listings via SerpApi (regional Google Shopping) or eBay Browse API matching the session country and currency.
- **FR-20: Condition Discrimination:** Differentiates new replacement prices (retail brand new) from used market values (used / pre-owned seller listings).
- **FR-21: Prohibition of Digital Substitutes:** Explicitly excludes eBooks, Kindle editions, audiobooks, and study guides from physical book valuations.
- **FR-22: Provenance Linking:** Every non-null price must include source name, direct HTTPS product link, retrieval timestamp, and assumed condition.
- **FR-23: High-Value & Appraisal Thresholds:** Books or artwork exceeding configurable per-currency appraisal thresholds (e.g., INR 80,000, USD 1,000) or user-marked first editions are marked `needs_appraisal` and excluded from automatic claim totals.
- **FR-24: Missing Price Handling:** If no live physical listing is found, price is left as `null` with a documented reason; prices are never fabricated or estimated by an LLM.

### 2.7 Non-Book Object Detection & Valuation
- **FR-25: Multi-Category Belongings Detection:** Proposes non-book physical objects (furniture, bookshelves, desks, chairs, lamps, electronics, rugs, artwork).
- **FR-26: Artwork Appraisal Enforcement:** Artwork is automatically assigned `status: "needs_appraisal"` and excluded from automatic totals unless verified by an appraiser.
- **FR-27: Non-Book Replacement Range:** Brand and model searches retrieve low and high physical replacement prices. Unverified models leave prices `null`.

### 2.8 Room Geometry & Dimensions
- **FR-28: Rectangular Room Calculation:** Computes floor area ($L \times W$) and wall area ($2H(L + W)$) in both $\text{m}^2$ and $\text{ft}^2$.
- **FR-29: Irregular Polygon Room Calculation:** Computes irregular floor area using Gauss's area formula (Shoelace formula) and wall area via perimeter $\times H$.
- **FR-30: Separation of Shelved Wall Area:** Shelved wall area is tracked independently and never erroneously added to total wall area.
- **FR-31: Unverified Observation Disclosure:** Uncalibrated camera estimations are stamped as `user_reported_during_sweep` with explicit low confidence (0.30).

### 2.9 Financial Totals & Human Review Queue
- **FR-32: Deterministic Financial Aggregation:** All totals (counts, replacement sums, used sums, item ranges, unpriced counts) are computed strictly via deterministic Python code. No LLM touches final loss calculations.
- **FR-33: Comprehensive Review Queue:** Automatically flags any record with unreadable spines, low identification confidence (<75%), missing metric scale, unverified prices, appraisal thresholds, or unestablished room geometry.

### 2.10 Reporting & Deliverable Generation
- **FR-34: Canonical Claim Packet JSON:** Emits `claim_packet.json` adhering to strict Pydantic v2 schemas (`extra='forbid'`).
- **FR-35: Standalone HTML Report:** Renders a responsive, accessible, printable `claim_report.html` with escaped markup.
- **FR-36: Professional PDF Report:** Builds `claim_report.pdf` using ReportLab with clean tabular layouts, summary metric cards, review queues, and disclaimers.
- **FR-37: Complete Archive Download:** Generates a downloadable ZIP containing `claim_packet.json`, `claim_report.html`, `claim_report.pdf`, and all referenced JPEG evidence frames.

---

## 3. Non-Functional Requirements

| Metric / Attribute | Specification | Current System Behavior |
|---|---|---|
| **Accuracy: Book Count** | Within 5% of true count | Supported by ORB homography tracking; unverified in physical rooms. |
| **Accuracy: Title Identification** | $\ge 70\%$ correct on legible spines | High on clear text via Open Library; unreadable spines left null. |
| **Accuracy: Confident Misidentification** | $\le 3\%$ across eligible items | Filtered via strict 0.75-0.82 confidence thresholds and review queue. |
| **Accuracy: Spine Dimensions** | Within 15% error with scale | Verified mathematically via coplanar reference scaling. |
| **Accuracy: Book Pricing** | Within 25% of verified listings | Sourced directly from live Google Shopping / eBay physical listings. |
| **Accuracy: Non-Book Detection** | $\ge 80\%$ recall with correct category | Supported via multimodal VLM and local contour proposal stages. |
| **Accuracy: Room Area** | Floor $\le 10\%$, Wall $\le 15\%$ error | Tape-measured inputs evaluated deterministically; monocular RGB uncalibrated. |
| **Latency: Post-Sweep Finalization** | Under 5 minutes (300 seconds) | Local synthetic finalization: <2 seconds; external API timeout budgeted. |
| **Security & Privacy** | OWASP Top 10 compliance | Path traversal protection, HTML escaping, bearer access key, local processing default. |
| **Data Integrity** | Cryptographic traceability | Every book/item links to UUID-named persistent JPEG file. |

---

## 4. Explicit Client Restrictions

1. **No Fabricated Prices:** Financial valuations must never be generated by LLM estimations. An item with no market listing must remain `null`.
2. **No Hallucinated Book Titles:** Titles cannot be invented if spine text is illegible or unverifiable.
3. **No Synthetic Barcode Scanning Bypass:** The application must inspect spines visually from continuous video sweep; it cannot require individual barcode scanning.
4. **No Single-Item Photography Requirement:** The user must be able to inventory entire shelves in continuous sweeps rather than taking isolated catalogue photos.
5. **No Editing of Demo Footage:** Demo recording must be continuous and unedited (under 6 minutes).

---

## 5. Client Requirements Traceability Matrix

| Req ID | Requirement Description | Priority | Current Implementation | Evidence Location | Gap / Weakness | Proposed Fix | Status |
|---|---|---|---|---|---|---|---|
| **REQ-01** | Live browser camera sweep | Critical | WebRTC `getUserMedia` with canvas JPEG capture every 2.3s | `frontend/app.js:29`, `backend/api.py:67` | Requires HTTPS on LAN | Document HTTPS proxy requirement | **Verified** |
| **REQ-02** | Voice assistant & guidance | High | Web Speech API TTS & speech recognition | `frontend/app.js:11-28` | Browser-dependent speech recognition | Added robust natural command parsing | **Verified** |
| **REQ-03** | Upright and stacked book detection | Critical | Dual-morphology Canny edge proposals & Gemini VLM | `backend/vision.py:35` | Stacked books previously rejected | Updated aspect checks for both orientations | **Verified** |
| **REQ-04** | Spine OCR & catalogue verification | Critical | Tesseract CLAHE + multi-PSM; Open Library Search API | `backend/vision.py:85`, `backend/catalog.py:10` | Long subtitles failed similarity | Subtitle normalization added | **Verified** |
| **REQ-05** | Homography tracking & deduplication | High | ORB feature matching + RANSAC homography + IoU | `backend/tracker.py:5-39` | Fast camera pans degrade homography | Warnings emitted; review queue flagged | **Verified** |
| **REQ-06** | Metric spine sizing | High | Coplanar reference ratio `px -> cm` | `backend/geometry.py:4-15` | Horizontal books inverted H/T | Sizing takes max as H, min as T | **Verified** |
| **REQ-07** | Live physical marketplace pricing | Critical | SerpApi Google Shopping & eBay Browse physical listings | `backend/pricing.py:39-98` | Strict currency prefix rejected EU prices | Enhanced regex currency symbol parser | **Verified** |
| **REQ-08** | Non-book object detection & ranges | Medium | Gemini VLM + local contour proposals; eBay brand search | `backend/vision.py:62`, `backend/pricing.py:99` | Offline mode lacked non-books | Added `local_item_candidates` | **Verified** |
| **REQ-09** | Room dimensions & area calculation | Medium | Rectangular + Irregular Shoelace formula | `backend/calculations.py:6-23` | Irregular rooms lacked perimeter wall math | Added polygon perimeter wall area | **Verified** |
| **REQ-10** | High-value & rare book appraisal | High | Configurable currency thresholds + user flags | `backend/pipeline.py:141`, `backend/api.py:123` | Unlisted currencies threw KeyError | Added safe dict lookup fallback | **Verified** |
| **REQ-11** | Canonical JSON claim packet | Critical | Pydantic v2 models with `extra='forbid'` | `backend/schemas.py:148` | None | Fully verified by schema tests | **Verified** |
| **REQ-12** | PDF & HTML report generation | Critical | ReportLab PDF generator + escaped HTML report | `backend/reporting.py:7-195` | PDF generation was missing | Implemented `pdf_report` with ReportLab | **Verified** |
| **REQ-13** | Traceable evidence frame storage | Critical | Persistent JPEG storage under `frames/` | `backend/store.py:12-36` | Evidence validation required | Verified via `validate_evidence` | **Verified** |
