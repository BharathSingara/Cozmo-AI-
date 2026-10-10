# REST API Reference — Library Contents Claim Agent

## 1. Authentication & Security

All API endpoints under `/api/*` require an authorization header if `APP_ACCESS_KEY` is configured in the environment:

```http
X-Access-Key: <APP_ACCESS_KEY>
```

If `APP_ACCESS_KEY` is set and the request lacks or mismatches the key, the server responds immediately with:
```http
HTTP/1.1 401 Unauthorized
```

Session identifiers are randomly generated 32-character hexadecimal UUIDv4 strings. File path access is strictly sanitized using regular expressions (`[0-9a-f]{32}` and `frames/[a-zA-Z0-9_-]+\.jpg`), preventing directory traversal attacks.

---

## 2. API Endpoints

### 2.1 System Health
```http
GET /api/health
```
Returns system operational status and enabled integration capabilities.

**Response:** `200 OK`
```json
{
  "ok": true,
  "remote_vision_enabled": false,
  "external_lookups_enabled": false
}
```

---

### 2.2 Create Sweep Session
```http
POST /api/sessions
Content-Type: application/json
```
Initializes a new claim session with configured market country and currency.

**Request Body:**
```json
{
  "country": "IN",
  "currency": "INR",
  "device": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)..."
}
```

**Supported Markets:**
| Country Code | Currency Code | Primary Marketplace |
|---|---|---|
| `IN` | `INR` | Google Shopping (India) via SerpApi |
| `US` | `USD` | Google Shopping / eBay US |
| `GB` | `GBP` | Google Shopping / eBay UK |
| `CA` | `CAD` | Google Shopping / eBay Canada |
| `AU` | `AUD` | Google Shopping / eBay Australia |
| `DE` | `EUR` | Google Shopping / eBay Germany |
| `FR` | `EUR` | Google Shopping / eBay France |

**Response:** `201 Created`
```json
{
  "id": "5f1b2c3d4e5f60718293a4b5c6d7e8f9",
  "packet": {
    "sweep": {
      "id": "5f1b2c3d4e5f60718293a4b5c6d7e8f9",
      "captured_at": "2026-10-09T16:00:00Z",
      "device": "Mozilla/5.0...",
      "duration_s": 0.0,
      "country": "IN",
      "currency": "INR",
      "finished_at": null
    },
    "room": {},
    "books": [],
    "items": [],
    "totals": {
      "book_count": 0,
      "books_identified": 0,
      "books_unidentified": 0,
      "currency": "INR"
    },
    "review_queue": []
  }
}
```

---

### 2.3 Ingest Camera Frame
```http
POST /api/sessions/{sid}/frames?shelf=Shelf%20A&reference_cm=15.0&reference_px=150.0
Content-Type: image/jpeg
```
Uploads a binary JPEG frame sampled during the continuous sweep.

**Query Parameters:**
- `shelf` *(string, default "Shelf A")*: Identifier of current shelf unit.
- `reference_cm` *(float, optional)*: Known physical measurement of coplanar reference marker.
- `reference_px` *(float, optional)*: Pixel span of reference marker in uploaded image.

**Request Body:** Raw binary JPEG bytes (Max size: 4,000,000 bytes).

**Response:** `200 OK`
```json
{
  "packet": { ... },
  "frame_ref": "frames/8b4f1c9d2e3a4567890123456789abcd.jpg",
  "quality": {
    "blur_score": 124.5,
    "glare_fraction": 0.012,
    "dark_fraction": 0.038,
    "warnings": [],
    "usable": true
  },
  "new_books": 4,
  "new_items": 1
}
```

---

### 2.4 Update Room Geometry
```http
POST /api/sessions/{sid}/room
Content-Type: application/json
```
Records tape-measured room dimensions or polygon boundaries verified during the sweep.

**Request Body (Rectangular):**
```json
{
  "length_m": 4.5,
  "width_m": 3.2,
  "height_m": 2.7,
  "shape": "rectangular",
  "scale_method": "user_reported_during_sweep",
  "shelved_wall_area_m2": 6.8,
  "reference_frame": "frames/8b4f1c9d2e3a4567890123456789abcd.jpg"
}
```

**Request Body (Irregular Polygon):**
```json
{
  "height_m": 2.7,
  "shape": "irregular",
  "scale_method": "user_reported_during_sweep",
  "polygon_points": [
    [0.0, 0.0],
    [5.0, 0.0],
    [5.0, 3.0],
    [2.0, 3.0],
    [2.0, 4.0],
    [0.0, 4.0]
  ]
}
```

**Response:** `200 OK`
```json
{
  "length_m": 4.5,
  "width_m": 3.2,
  "height_m": 2.7,
  "floor_area_m2": 14.4,
  "floor_area_ft2": 155.0,
  "wall_area_m2": 41.58,
  "wall_area_ft2": 447.563,
  "shelved_wall_area_m2": 6.8,
  "shape": "rectangular",
  "scale_method": "user_reported_during_sweep",
  "confidence": 0.3,
  "uncertainty": "User-supplied dimensions not independently verified"
}
```

---

### 2.5 Submit Operator Correction
```http
POST /api/sessions/{sid}/corrections
Content-Type: application/json
```
Submits a verbal or UI operator intervention. Preserved in append-only `audit_log`.

**Supported Commands:**
- `exclude_shelf`: `{ "command": "exclude_shelf", "shelf": "Shelf A" }`
- `exclude_item`: `{ "command": "exclude_item", "ref_id": "book_12345" }`
- `first_edition`: `{ "command": "first_edition", "ref_id": "book_12345" }`
- `art_print`: `{ "command": "art_print", "ref_id": "item_67890" }`
- `correct_title`: `{ "command": "correct_title", "ref_id": "book_12345", "value": "To Kill a Mockingbird" }`
- `missed_shelf`: `{ "command": "missed_shelf" }`

**Response:** `200 OK` returns updated canonical packet.

---

### 2.6 Finalize Sweep Session
```http
POST /api/sessions/{sid}/finish
```
Locks the session against further frames, awaits in-flight asynchronous enrichment tasks (up to 240 seconds), validates that all referenced evidence frames exist on disk, computes final deterministic totals, generates `claim_packet.json`, `claim_report.html`, and `claim_report.pdf`.

**Response:** `200 OK`
```json
{
  "packet": { ... },
  "report": "/api/sessions/5f1b2c3d4e5f60718293a4b5c6d7e8f9/report",
  "pdf_report": "/api/sessions/5f1b2c3d4e5f60718293a4b5c6d7e8f9/report/pdf",
  "download": "/api/sessions/5f1b2c3d4e5f60718293a4b5c6d7e8f9/archive"
}
```

---

### 2.7 Download Claim Packet JSON
```http
GET /api/sessions/{sid}/packet
```
**Response:** `200 OK` (`application/json`) with `Content-Disposition: attachment; filename="claim_packet.json"`.

---

### 2.8 View / Download HTML Report
```http
GET /api/sessions/{sid}/report
```
**Response:** `200 OK` (`text/html`) with fully styled, printable standalone claim report.

---

### 2.9 Download PDF Report
```http
GET /api/sessions/{sid}/report/pdf
```
**Response:** `200 OK` (`application/pdf`) with `Content-Disposition: attachment; filename="claim_report.pdf"`.

---

### 2.10 Retrieve Evidence Image
```http
GET /api/sessions/{sid}/evidence/{filename}
```
**Response:** `200 OK` (`image/jpeg`) returns authenticated evidence frame.

---

### 2.11 Download Complete Evidence Archive
```http
GET /api/sessions/{sid}/archive
```
**Response:** `200 OK` (`application/zip`) containing:
- `claim_packet.json`
- `claim_report.html`
- `claim_report.pdf`
- `frames/*.jpg`

---

### 2.12 Delete Session
```http
DELETE /api/sessions/{sid}
```
Cancels pending background tasks and permanently wipes session directory and all saved evidence frames from disk.

**Response:** `204 No Content`.
