# Setup and Configuration Guide — Library Contents Claim Agent

## 1. System Requirements & Prerequisites

The application is written in clean, cross-platform Python and requires no external database servers or complex microservice infrastructure.

### Operating Systems
- **Windows:** 10 / 11 / Server 2022+ (PowerShell or Command Prompt).
- **Linux:** Ubuntu 22.04+, Debian 12+, RHEL 9+.
- **macOS:** 13 (Ventura) or 14 (Sonoma).

### Software Dependencies
1. **Python:** 3.10 or newer (tested and verified on Python 3.13 and 3.14).
2. **Tesseract OCR (Recommended for live spine text extraction):**
   - *Windows:* Download official installer from UB Mannheim (`https://github.com/UB-Mannheim/tesseract/wiki`) and ensure `tesseract.exe` is added to system `PATH`.
   - *Ubuntu/Debian:* `sudo apt-get update && sudo apt-get install -y tesseract-ocr`
   - *macOS:* `brew install tesseract`

---

## 2. Quickstart Installation (Under 15 Minutes)

### Step 1: Clone or Extract Repository
```bash
cd library-claim-agent
```

### Step 2: Create and Activate Virtual Environment
**Windows PowerShell:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Python Dependencies
```bash
pip install -r requirements.txt
```

Verify ReportLab and pytest-asyncio installation:
```bash
python -c "import reportlab, cv2, fastapi, pydantic; print('All core libraries ready!')"
```

### Step 4: Configure Environment Variables
Copy the example configuration file:
**Windows:**
```powershell
copy .env.example .env
```
**Linux / macOS:**
```bash
cp .env.example .env
```

### Step 5: Launch Local Server
```bash
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```
Open **http://127.0.0.1:8000** in Google Chrome or Microsoft Edge.

---

## 3. Environment Variables Reference

| Variable Name | Default Value | Purpose & Security Implications |
|---|---|---|
| `APP_ACCESS_KEY` | *empty* | Shared bearer secret required in `X-Access-Key` header. Leave empty for open local development; set in shared networks. |
| `ALLOW_REMOTE_VISION` | `false` | Must be explicitly set to `true` to transmit camera frames to Google Gemini API. Requires room owner consent. |
| `GEMINI_API_KEY` | *empty* | Google AI Studio API key for Gemini multimodal vision. Kept in memory only; never committed to Git. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model variant used for visual bounding box generation. |
| `ALLOW_EXTERNAL_LOOKUPS` | `false` | Set to `true` to allow outbound HTTP requests to Open Library, SerpApi, or eBay. |
| `SERPAPI_KEY` | *empty* | Account key for SerpApi to retrieve regional Google Shopping physical product listings. |
| `EBAY_BROWSE_TOKEN` | *empty* | OAuth user access token for eBay Browse API (alternative price provider). |
| `DATA_ROOT` | `./data/sessions` | Filesystem directory where private session states and raw JPEG frames are persisted. |
| `MAX_FRAMES_PER_SESSION`| `200` | Safety limit on total uploaded frames per sweep to prevent disk exhaustion. |
| `PRICE_TIMEOUT_SECONDS` | `6` | Outbound HTTP timeout for marketplace price retrieval. |
| `APPRAISAL_THRESHOLD_INR`| `80000` | Local currency valuation threshold above which items are excluded from totals and flagged for appraisal. |
| `APPRAISAL_THRESHOLD_USD`| `1000` | US Dollar threshold for mandatory human appraisal routing. |
| `APPRAISAL_THRESHOLD_GBP`| `800` | British Pound threshold. |
| `APPRAISAL_THRESHOLD_EUR`| `900` | Euro threshold. |
| `APPRAISAL_THRESHOLD_CAD`| `1400` | Canadian Dollar threshold. |
| `APPRAISAL_THRESHOLD_AUD`| `1600` | Australian Dollar threshold. |

---

## 4. Mobile Device Testing & HTTPS Setup

Modern mobile browsers strictly enforce the **Secure Context** policy: `navigator.mediaDevices.getUserMedia` is disabled on non-localhost HTTP connections.

To use a smartphone over a local Wi-Fi network:
1. **Option A: Trusted Local Reverse Proxy (Recommended):**
   Use tools like `caddy` or `mkcert` to serve HTTPS with a local CA certificate:
   ```bash
   caddy reverse-proxy --from https://my-laptop.local:8443 --to http://127.0.0.1:8000
   ```
2. **Option B: Secure Tunnel (e.g., ngrok / cloudflared):**
   ```bash
   ngrok http 8000
   ```
   Open the generated HTTPS URL on your mobile phone and grant camera and microphone permissions.

---

## 5. Verifying Installation & Tests

Execute the automated test suite to confirm all modules function correctly:
```bash
python -m pytest -v tests
```
All 36 tests should pass within 30 seconds.
