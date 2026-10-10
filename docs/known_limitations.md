# Known Limitations & Operating Boundaries — Library Contents Claim Agent

## 1. Physical & Optical Boundaries

### 1.1 Motion Blur & Rapid Camera Trajectory
- **Limitation:** Sweeping the camera across bookshelves at angular velocities exceeding ~30 degrees per second introduces severe motion blur.
- **System Behavior:** Laplacian variance drops below the usable threshold (<35). The frame is saved as persistent evidence to maintain temporal integrity, but candidate proposals are skipped to prevent false detections. The browser audio alerts the operator: *"Motion blur: slow down and hold the camera steady."*

### 1.2 Glossy Dust Jackets & Specular Reflection
- **Limitation:** High-gloss protective plastic sleeves and direct lighting produce white glare patches that obscure title typography.
- **System Behavior:** When saturated pixel fraction exceeds 9%, the agent advises: *"Glare detected: tilt the camera away from direct reflection."* Illegible titles are not guessed; they remain in the human review queue.

### 1.3 Occlusion & Oblique Angles
- **Limitation:** Book spines viewed at steep angles (>45 degrees from the shelf normal) experience significant perspective compression, making character segmentation difficult for OCR.
- **Operator Best Practice:** Operators should hold the device perpendicular to the shelf plane, walking parallel to the shelving unit.

---

## 2. Geometric & Metric Measurement Boundaries

### 2.1 Monocular Scale Ambiguity
- **Limitation:** Standard mobile RGB video cannot measure physical distance or size without an established metric scale or calibrated depth sensor (e.g., iPhone LiDAR).
- **System Safeguard:** Physical book thickness and height remain `null` unless the operator supplies an exact coplanar reference span ($\text{cm}$ and $\text{px}$) for that shelf. Fabricated dimensions are strictly prohibited.

### 2.2 Shelf Run Gaps and Book Lean
- **Limitation:** Calculating shelf run as the mathematical sum of individual book thicknesses assumes books stand perfectly plumb without open gaps.
- **System Safeguard:** Shelf run is computed only when every book on the shelf has an established thickness; partial shelf sums are withheld.

### 2.3 Monocular Room Reconstruction
- **Limitation:** Uncalibrated camera video cannot accurately reconstruct 3D architectural floor plans.
- **System Safeguard:** Room dimensions are accepted as operator-reported tape measurements during the sweep. The system stamps them as `scale_method: "user_reported_during_sweep"` with low confidence (0.30) and explicit uncertainty warnings.

---

## 3. Bibliographic & OCR Boundaries

### 3.1 Stylized, Embossed, and Calligraphic Typography
- **Limitation:** Fantasy, vintage, or artistic bindings with heavily stylized, embossed, or cursive lettering may yield garbled OCR strings from Tesseract.
- **System Safeguard:** Text similarity matching against Open Library requires $\ge 82\%$ confidence. Low-confidence matches are discarded, and the user can verbally correct the title via `"Title is [Title]"` to trigger immediate re-verification.

### 3.2 Edition & Printing Disambiguation
- **Limitation:** A physical spine rarely displays the ISBN barcode or printing impression number. Open Library provides work-level metadata (title, primary author) but cannot definitively prove whether a volume is a valuable first printing or a standard reprint.
- **System Safeguard:** The system assigns work-level status only and marks editions as `"First edition (user assertion; unverified)"` if claimed by the user. Sourced listings exceeding per-currency appraisal thresholds are excluded from automated monetary totals.

---

## 4. Market Pricing & Listing Boundaries

### 4.1 Out-of-Print & Antiquarian Availability
- **Limitation:** Books out of print for decades may lack active retail listings on Google Shopping or current Buy-It-Now eBay listings.
- **System Safeguard:** If no live physical listing is found, the price remains `null` with `unavailable_reason: "No verifiable physical-book listing matches"`. The item is listed as unpriced in the summary totals and routed to human review.

### 4.2 Condition Grading Discrepancies
- **Limitation:** Sourced secondary market listings reflect the condition advertised by third-party sellers ("Like New", "Good", "Acceptable"), not a forensic inspection of the policyholder's actual copy.
- **System Safeguard:** The claim report explicitly flags: *"Used prices reflect listed seller condition, not inspected condition."*

---

## 5. Security & Legal Disclaimer

- **Prototype Status:** The application is an evidentiary aid for insurance intake, not an official sworn appraisal or financial guarantee.
- **Authentication:** `APP_ACCESS_KEY` provides shared bearer security suitable for private development and local network audits; production multi-tenant deployments require OAuth2 / OIDC authentication and encrypted database storage.
- **Adjuster Sign-Off:** All financial claim packets require final inspection, coverage review, and approval by an authorized insurance claims adjuster before claim settlement.
