# Library Contents Claim Agent

**Working modular prototype, with unverified real-world accuracy.** A mobile/desktop browser records camera **frames live** during one continuous sweep, receives browser speech guidance, and updates a FastAPI inventory. Each detected candidate has persistent evidence; a conservative pipeline performs OCR, catalogue verification, metric sizing *only with an established scale*, market-listing retrieval, deduplication, deterministic totals, human-review routing, and a JSON + HTML report. **This does not yet demonstrate the client's accuracy targets or a real-room demo.**

## Quick start (Python 3.10+; tested on 3.13)

```bash
cd library-claim-agent
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Ubuntu/Debian for actual OCR: sudo apt-get install tesseract-ocr
cp .env.example .env           # Windows: copy .env.example .env
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** in Chrome/Edge and grant camera access. Microphone speech recognition and synthesized speech depend on browser/OS support; typed correction is always available. Browser speech recognition may use a vendor's online speech service. For mobile over a LAN, **serve HTTPS** via a trusted reverse proxy; plain LAN HTTP is not a secure context for `getUserMedia`. Keep the server local unless HTTPS plus authentication has been configured. No prerecorded video input masquerades as live capture.

For better book/non-book detection, put `GEMINI_API_KEY` in `.env`, set `ALLOW_REMOTE_VISION=true` **with room owner's consent**. Frames are then sent to Google's Gemini API, and remote model calls may be charged. For book ID/valuation, set `ALLOW_EXTERNAL_LOOKUPS=true`, and provide `SERPAPI_KEY` for region-local Google Shopping listings or `EBAY_BROWSE_TOKEN` for supported eBay regions. The default path does **not** transmit camera images to a vendor. No real credentials were used in the development test. The `.env` file is ignored by Git. Read `.env.example` for the complete configuration.

The fast offline contour detector is **only a conservative proposal generator** and is not claimed as an accurate per-book instance detector. Models, networks, real camera devices and local book availability affect outputs. If no valid price, metric scale or reliable identification exists, its value remains `null` and is flagged for review. The total of available prices is **not** the total replacement value of an unpriced library.

## Live workflow

1. Choose country and currency; click **Start sweep**, allow camera (and microphone if desired).
2. Sweep shelves slowly left to right with readable spines, and then furniture, walls and corners. Use **Next shelf** to distinguish different shelf units/segments. Camera frames sample every ~2.3 seconds; the user should finish in one pass, preferably under 3 minutes. Camera stays live even if a frame processing request is in flight.
3. Quality flags prompt recapture in the **same** sweep. Optional metric scale requires a correctly measured coplanar reference and its pixel span in the *uploaded* frame; otherwise leave dimensions blank.
4. Correct records using their per-item buttons, the command box, or speech. Commands include “skip that shelf”, “that is a first edition”, “that painting is a print”, “next shelf”, and “you missed the bottom shelf”. All changes are audit logged; unverified claims do not become verified valuations. `Pause` suspends frame sampling, not camera preview.
5. Optionally record room dimensions as **user-reported during sweep** with a rectangular-shape confirmation. This is *not* automatic monocular room reconstruction and has low confidence. Unconfirmed shapes produce unavailable wall/floor areas.
6. Click **Finish & build claim** and download the JSON, HTML or full ZIP (including stored JPEG evidence). The server waits for queued enrichment up to 240 seconds, then records timing and flags unfinished work. Delete test sessions using the Delete button.

### REST API

All `/api/*` endpoints require `X-Access-Key: <APP_ACCESS_KEY>` only when `APP_ACCESS_KEY` is configured. Sessions use unpredictable UUID4 hex IDs; same-origin transport by default. No claims/personal data leave the local server unless optional model/catalogue/market integrations are enabled.

| Route | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Capability flags |
| `/api/sessions` | POST | `{country:"IN",currency:"INR",device:"browser"}` |
| `/api/sessions/{sid}` | GET | Current live packet |
| `/api/sessions/{sid}/frames?shelf=Shelf%20A` | POST | JPEG binary `Content-Type:image/jpeg`, 4MB max; optional `reference_cm`,`reference_px` |
| `/api/sessions/{sid}/room` | POST | Confirm shape/room observations and evidence ref |
| `/api/sessions/{sid}/corrections` | POST | `{command,ref_id,value,shelf}` |
| `/api/sessions/{sid}/finish` | POST | Wait, validate evidence, finalize JSON + HTML + PDF |
| `/api/sessions/{sid}/packet` | GET | Canonical `claim_packet.json` |
| `/api/sessions/{sid}/report` | GET | Canonical `claim_report.html` |
| `/api/sessions/{sid}/report/pdf` | GET | Canonical `claim_report.pdf` (ReportLab) |
| `/api/sessions/{sid}/evidence/{filename}` | GET | Protected image |
| `/api/sessions/{sid}/archive` | GET | Evidence and output ZIP (JSON, HTML, PDF, JPEGs) |
| `/api/sessions/{sid}` | DELETE | Delete entire private test session |

Interactive OpenAPI docs: `/docs`. Pydantic v2 defines and validates all packet fields and API inputs.

## Architecture

```text
Mobile/desktop browser (getUserMedia live frames + Web Speech API + UI)
    |
    v JPEG POST + commands; GET live inventory
FastAPI [session management; access key; frame/evidence persistence]
    |
    +-- frame quality: Laplacian blur, overexposure and dark-pixel warnings
    +-- vision: optional Gemini 2.5 Flash JSON boxes, else OpenCV proposals
    +-- tracking: ORB registration + homography + one-to-one spatial matching
    +-- OCR: local Tesseract rotations -> Open Library work verification
    +-- measurements: established coplanar cm/pixel reference or NULL
    +-- price provider: SerpApi regional shopping / eBay physical listings
    +-- room geometry: explicit verified rectangular inputs or NULL
    +-- deterministic totals + separate confidence + review reasons
    +-- validated claim JSON -> escaped HTML + evidence ZIP
    |
    v
 data/sessions/<uuid>/{state.json,claim_packet.json,claim_report.html,frames/*.jpg}
```

Stage timings and external-call counts are included in the packet. Google voice/model and marketplace actual usage cost is not automatically returned by these integrations, and therefore is reported as **unknown**, rather than invented. See `docs/architecture.md` and `docs/failure_log.md`.

### Measurements and finance integrity

- Frame bounding-box pixels are **never** converted to centimetres without valid reference values. An image-plane ratio with a known same-depth dimension gives approximate book sizes and estimated uncertainty. Different-depth perspective can introduce substantial unmeasured error. Shelf run is summed spine thickness only if **every included book has metric thickness**; gaps and book lean are not modeled.
- Accurate room length/width/height cannot be recovered from ordinary uncalibrated camera video. The current route accepts observations confirmed during the same sweep and identifies them as **self-reported**. Rectangular floor `L×W`; walls `2H(L+W)`; shelved area is separate. Irregular room formulas exist for polygon area, but no reliable camera reconstruction is implemented.
- Physical new and used values come from **live external listings** only. Google Shopping results without second-hand markers are considered new listings (verify manually); eBay condition filtering is explicit. ISBN/edition inference is **never** invented from a work-level catalogue match. `convert()` requires a documented exchange rate; the live pricing path chooses local currency listings instead of performing undocumented FX conversion. Used prices are seller asking prices, not appraised transaction values. First editions and original artwork require appraisal. Sourced listings exceeding configurable per-currency `APPRAISAL_THRESHOLD_<CURRENCY>` are indicative only and excluded from monetary totals until reviewed.
- Pydantic rejects prices without a source, URL, timestamp and currency. Missing amounts are `null`; only available, currency-matching, nonexcluded amounts enter totals. Book count includes unidentified candidates, so local detector false positives are a key risk.

## Testing, evaluation and real-world limitations

```bash
python -m pytest -q tests
python -m scripts.evaluate --truth data/your_real_ground_truth.csv --room-json data/your_real_room.json --out data/real_evaluation.json
ALLOW_EXTERNAL_LOOKUPS=true SERPAPI_KEY=... python -m scripts.second_country --input data/books_to_price.csv --country-a IN --country-b US --out data/second_country_live.csv
```

The spreadsheet `data/ground_truth_and_results_template.xlsx` includes **blank** ground-truth collection sheets for 60 books, 20 spines, 15 prices, 8 other items, room geometry and 10 cross-country pairs. Populate only after capturing and independently checking a permitted real room. `data/books_to_price.csv` is a blank ten-book input, not completed market results. No real-camera or real-market quality claims are supported by synthetic tests.

**Engineering verification:** 36 automated tests passed (100% pass rate) in the build environment, including unit, integration, failure, horizontal/stacked book detection, offline non-book proposal generation, irregular room geometry, subtitle normalization, title correction re-enrichment, ReportLab PDF report generation, and full API/JSON/HTML/PDF/archive/deletion sweeps. Post-sweep packet generation completes in 1.8–3.2 seconds in local synthetic tests (well within the client's 5-minute SLO). Details: `docs/failure_log.md` and `docs/testing.md`.

## Deliverables & Documentation Suite

1. **Source Code & API Server:** Complete modular FastAPI backend, vanilla WebRTC/Web Speech frontend, deterministic geometry and pricing modules.
2. **Comprehensive Technical Documentation:**
   - [Requirements Specification](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/requirements.md)
   - [System Architecture](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/architecture.md)
   - [Data Flow & Sequences](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/data_flow.md)
   - [REST API Reference](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/api_reference.md)
   - [Setup & Configuration](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/setup_and_configuration.md)
   - [Testing & Evaluation](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/testing.md)
   - [Measurement Methodology](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/measurement_methodology.md)
   - [Pricing Methodology](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/pricing_methodology.md)
   - [Engineering Failure Log](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/failure_log.md)
   - [Known Limitations](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/known_limitations.md)
   - [Demo Recording Checklist](file:///c:/Projects/library_claim_agent_complete_source/library-claim-agent/docs/demo_checklist.md)
3. **Claim Packet Deliverables (`sample_claim/`):**
   - Canonical `claim_packet.json`
   - Standalone `claim_report.html`
   - Vector `claim_report.pdf` (ReportLab)
   - Referenced persistent JPEG evidence (`frames/synthetic_frame.jpg`)
4. **Evaluation Deliverables (`data/` & `scripts/`):**
   - Field collection workbook: `data/ground_truth_and_results_template.xlsx`
   - Automated accuracy evaluator: `scripts/evaluate.py`
   - Cross-country price comparison script: `scripts/second_country.py`
   - Synthetic sample claim generator: `scripts/create_sample_claim.py`

### Reference application reuse review

Reference: `https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/voice_ai_agents/insurance_claim_live_agent_team` (public README inspected October 9, 2026). It is an FNOL voice-first claim intake tool using FastAPI, a Gemini Live voice channel and Google ADK structured extraction. **Retained conceptually:** FastAPI/browser UI, voice interaction, structured claim packet, operator/adjuster guidance. **Changed:** domain-specific modular frame pipeline, evidence-anchored CV/OCR, explicit geometry/price uncertainty, physical-market price links, independent testability. **Not reused:** ADK graph, its FNOL policy classification, and conversational-only claims extraction. Terminal clone and actual reference execution were unavailable (DNS/network failure). Do not imply this repository is the reference's code fork.

### Security caveats

Local prototype only. `APP_ACCESS_KEY` is a shared bearer secret, not policyholder authentication or an audited authorization system. At-rest JPEGs/JSON are not encrypted. Camera/video includes sensitive interiors. Configure TLS, user isolation, retention, logging, formal privacy policy and third-party data processing consent before any commercial deployment. The frontend/Web Speech recognizer and provider APIs have service-dependent privacy policies. Saved files are in `DATA_ROOT` (`./data/sessions` by default); DELETE removes a test session. Do not deliberately film people or personal documents.
