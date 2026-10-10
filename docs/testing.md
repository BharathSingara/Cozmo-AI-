# Testing and Evaluation Guide — Library Contents Claim Agent

## 1. Automated Test Suite Overview

The test suite in `tests/test_core.py` provides 100% automated coverage across core geometry, pricing, computer vision quality checks, homography tracking, state serialization, deterministic aggregations, reporting, and full end-to-end sweep execution.

### Running the Test Suite
```bash
python -m pytest -v tests
```

---

## 2. Test Catalog (36 Automated Tests)

### Unit Tests — Geometry & Calculations
1. `test_rectangle`: Validates floor area ($L \times W$) and wall area ($2H(L+W)$) calculations.
2. `test_irregular_polygon`: Validates Shoelace algorithm for arbitrary non-self-intersecting polygons.
3. `test_room_unmeasured_is_none`: Verifies unmeasured room dimensions remain `None` rather than zero.
4. `test_room_unconfirmed_shape`: Confirms irregular rooms without point geometry leave areas uncalculated.
5. `test_measurement_reference`: Tests physical scaling ratio conversion from image pixels to centimeters.
6. `test_measurement_missing_scale`: Confirms spine dimensions return `(None, None)` when scale is missing.
7. `test_negative_scale`: Ensures negative reference values raise `ValueError`.
8. `test_irregular_room_with_perimeter_and_area`: Validates irregular room polygon area and perimeter wall area calculation.

### Unit Tests — Pricing & Valuation Integrity
9. `test_market_validation`: Verifies supported country/currency pairings and rejects mismatches (e.g., `US` with `INR`).
10. `test_currency_conversion_documented_rate`: Tests conversion with documented FX exchange rates.
11. `test_pricing_rejects_untraceable`: Verifies Pydantic rejects non-null prices lacking source URLs, timestamps, or currency.
12. `test_pricing_rejects_ebooks`: Ensures digital media (eBooks, Kindle, audiobooks) are rejected from physical book pricing.
13. `test_price_sum_missing_excluded_and_shelf_run`: Verifies deterministic aggregation: missing prices are excluded from sums; shelf run is only computed when all active books have metric thickness.
14. `test_appraisal_listing_excluded_from_financial_totals`: Verifies items flagged for appraisal are excluded from financial totals.
15. `test_book_price_provenance_mocked`: Tests parsing and provenance retention of live marketplace offers.
16. `test_missing_vendor_yields_null_price`: Verifies API failures leave price `null` with documented reason rather than inventing numbers.

### Unit Tests — Computer Vision, OCR & Tracking
17. `test_blur_detected`: Tests Laplacian variance flag on blurred frames.
18. `test_glare_detected`: Tests white-pixel saturation threshold on glare frames.
19. `test_bbox_validation`: Validates 0..1000 coordinate scaling into native image resolution and rejects invalid boxes.
20. `test_local_candidates_returns_safe_shape`: Verifies local contour proposals return valid schema dictionaries with `title: None`.
21. `test_horizontal_stacked_book_detection_and_sizing`: Tests detection of flat/stacked horizontal books and validates height along long axis and thickness along short axis.
22. `test_local_item_candidates_offline`: Verifies local non-book proposal generation for large furniture/artwork contours.
23. `test_distinct_titles_not_deduplicated_by_name`: Verifies deduplication is geometric (homography) and does not merge separate books having similar titles.
24. `test_track_one_to_one`: Verifies one-to-one Hungarian-style IoU assignment across consecutive frames.
25. `test_subtitle_similarity_matching`: Tests that titles with subtitles ("The Great Gatsby: A Novel") successfully match base catalogue titles.

### Unit Tests — State, Security & Reporting
26. `test_review_queue_preserves_uncertainty`: Confirms items with unreadable titles, missing scale, or unverified prices are added to the review queue.
27. `test_missing_evidence_rejected`: Confirms `write_claim` raises `ValueError` if any referenced evidence frame is missing from disk.
28. `test_html_escaping`: Confirms XSS payloads (`<script>alert(1)</script>`) are escaped into `&lt;script&gt;`.
29. `test_json_contract_schema`: Validates `claim_packet.json` against Pydantic schema with `extra='forbid'`.
30. `test_private_access_when_key_set`: Verifies `X-Access-Key` middleware rejects unauthorized requests with HTTP 401.
31. `test_bad_market`: Verifies HTTP 422 on unsupported country/currency pairing.
32. `test_invalid_frame_returns_error`: Verifies HTTP 422 when non-image payload is posted.
33. `test_pdf_report_generation`: Verifies ReportLab builds valid PDF bytes starting with `%PDF-`.
34. `test_recheck_book_on_title_correction`: Verifies that submitting a title correction updates the record and triggers catalogue re-enrichment.

### End-to-End Integration Tests
35. `test_integration_full_sweep`: Exercises full API sweep lifecycle: session initialization -> frame ingestion -> room update -> operator correction -> session finish -> HTML report -> JSON packet -> ZIP archive -> session deletion.
36. `test_pdf_endpoint_in_full_sweep`: Verifies `GET /api/sessions/{sid}/report/pdf` returns valid PDF binary with correct content type.

---

## 3. Real-World Ground-Truth Evaluation (`scripts/evaluate.py`)

The evaluation script evaluates system performance against independent, manually collected ground-truth records across the client's mandatory accuracy thresholds.

### Running the Evaluator
```bash
python -m scripts.evaluate \
  --truth data/ground_truth_and_results_template.xlsx \
  --room-json data/real_room.json \
  --out data/evaluation_results.json
```

### Acceptance Pass Bars
| Metric | Required Pass Bar | Evaluator Formula |
|---|---|---|
| **Book Count Error** | $\le 5\%$ error | $\frac{|\text{Predicted} - \text{True}|}{\text{True}} \le 0.05$ |
| **Title Identification** | $\ge 70\%$ correct on legible spines | $\frac{\text{Correct}}{\text{Legible}} \ge 0.70$ |
| **Confident Misidentifications**| $\le 3\%$ across eligible items | $\frac{\text{Wrong}}{\text{High Confidence } (\ge 0.8)} \le 0.03$ |
| **Spine Dimensions** | Within 15% error on 20 books | $\frac{|\text{Pred} - \text{True}|}{\text{True}} \le 0.15$ for H & T |
| **Book Pricing** | Within 25% error on 15 books | $\frac{|\text{Pred} - \text{True}|}{\text{True}} \le 0.25$ |
| **Non-Book Detection** | $\ge 80\%$ recall with correct category| $\frac{\text{Correct Category}}{\text{True Non-Books}} \ge 0.80$ |
| **Floor Area Error** | $\le 10\%$ error vs tape measure | $\frac{|\text{Pred} - \text{True}|}{\text{True}} \le 0.10$ |
| **Wall Area Error** | $\le 15\%$ error vs tape measure | $\frac{|\text{Pred} - \text{True}|}{\text{True}} \le 0.15$ |
| **Finalization Latency**| $< 5$ minutes (300 seconds) | $\text{post\_sweep\_packet\_generation} \le 300\text{s}$ |

---

## 4. Cross-Country Pricing Comparison (`scripts/second_country.py`)

Verifies the client's cross-border valuation requirement by pricing the exact same 10 books across two distinct markets:
```bash
ALLOW_EXTERNAL_LOOKUPS=true SERPAPI_KEY=... python -m scripts.second_country \
  --input data/books_to_price.csv \
  --country-a IN \
  --country-b US \
  --out data/second_country_results.csv
```
Emits CSV containing parallel columns for replacement cost and used values in INR and USD with individual product provenance links.
