# Metric Measurement Methodology — Library Contents Claim Agent

## 1. Principles of Physical Measurement in Monocular RGB Vision

A fundamental law of projective computer vision is that an ordinary monocular RGB camera without active depth sensors (e.g., LiDAR, stereo cameras, structured light) suffers from **fundamental scale ambiguity**. An image of an object 20 cm tall at a distance of 1 meter produces the exact same pixel projection as an object 40 cm tall at a distance of 2 meters.

Therefore, the **Library Contents Claim Agent strictly prohibits estimating real-world metric dimensions without an established, coplanar reference scale**.

---

## 2. Book Spine Dimension Methodology

### 2.1 The Coplanar Reference Scale
To measure book spines accurately, an operator must place a known physical reference marker (e.g., a 15 cm ruler or calibrated target card) on the **exact same vertical focal plane** as the book spines.

The operator provides two parameters:
1. $\text{Ref}_{\text{cm}}$: Known real-world physical span in centimeters (e.g., $15.0\text{ cm}$).
2. $\text{Ref}_{\text{px}}$: Observed pixel span of that marker in the uploaded frame (e.g., $150\text{ px}$).

The image-plane scaling factor is computed as:
$$S = \frac{\text{Ref}_{\text{cm}}}{\text{Ref}_{\text{px}}} \quad (\text{cm / px})$$

### 2.2 Sizing Upright vs. Flat / Stacked Books
Given a book bounding box $[x_1, y_1, x_2, y_2]$:
- Width in pixels: $W_{\text{px}} = |x_2 - x_1|$
- Height in pixels: $H_{\text{px}} = |y_2 - y_1|$

Because books may be shelved upright (vertical) or stacked horizontally on top of each other:
- **Spine Height / Length:** Corresponds to the **longer** axis:
  $$\text{Height}_{\text{cm}} = \max(H_{\text{px}}, W_{\text{px}}) \times S$$
- **Spine Thickness:** Corresponds to the **shorter** axis:
  $$\text{Thickness}_{\text{cm}} = \min(H_{\text{px}}, W_{\text{px}}) \times S$$

### 2.3 Uncertainty Representation
Due to camera perspective, minor off-plane book recessions, and bounding box edge localization noise, all derived measurements include an explicit uncertainty margin (default 10%):
$$\text{Uncertainty} = \text{Dimension}_{\text{cm}} \times 0.10$$
Confidence is assigned based on scale precision ($0.70$ max for coplanar ratios).

If no valid scale reference is provided ($\text{Ref}_{\text{cm}} = \text{null}$ or $\text{Ref}_{\text{px}} = \text{null}$), dimensions remain `null` and the item is routed to the human review queue. Plausible guesses are never inserted.

---

## 3. Shelf Run Calculation

Total shelf run measures the linear shelf space occupied by books on a given shelving unit.

$$\text{Shelf Run (m)} = \frac{\sum_{b \in B_{\text{active}}} b.\text{spine\_thickness\_cm}}{100}$$

### Strict Completeness Rule
To prevent misleading partial lengths, **total shelf run is calculated only if 100% of the active books on that shelf possess a verified metric thickness**. If even a single book lacks thickness data, `shelf_run_m` is reported as `null` with a review note.

---

## 4. Room Geometry & Surface Area Methodology

### 4.1 Rectangular Room Calculation
When an operator verifies a rectangular room during the sweep with length $L$, width $W$, and ceiling height $H$:
- **Floor Area:**
  $$\text{Floor Area (m}^2\text{)} = L \times W$$
  $$\text{Floor Area (ft}^2\text{)} = \text{Floor Area (m}^2\text{)} \times 10.76391$$
- **Total Wall Area:**
  $$\text{Wall Area (m}^2\text{)} = 2H(L + W)$$
  $$\text{Wall Area (ft}^2\text{)} = \text{Wall Area (m}^2\text{)} \times 10.76391$$

### 4.2 Irregular Polygon Room Calculation
For L-shaped or non-rectangular rooms where 2D corner vertices $(x_i, y_i)$ are supplied:
- **Floor Area (Shoelace Formula):**
  $$\text{Floor Area} = \frac{1}{2} \left| \sum_{i=0}^{n-1} (x_i y_{i+1} - x_{i+1} y_i) \right| \quad (\text{with } x_n = x_0, y_n = y_0)$$
- **Total Wall Area:**
  $$\text{Perimeter} = \sum_{i=0}^{n-1} \sqrt{(x_{i+1} - x_i)^2 + (y_{i+1} - y_i)^2}$$
  $$\text{Wall Area} = \text{Perimeter} \times H$$

### 4.3 Shelved Wall Area Independence
The area of walls occupied by bookshelves ($\text{Shelved Wall Area}$) is recorded as an independent metric. **It is never added to total wall area**, as doing so would double-count wall surfaces in building repair estimates.

### 4.4 Data Provenance & Low Confidence Marking
Unless room dimensions are collected via verified architectural plans or calibrated LiDAR, camera-assisted or user-entered room dimensions are explicitly stamped in the claim packet as:
- `scale_method: "user_reported_during_sweep"`
- `confidence: 0.30`
- `uncertainty: "User-supplied dimensions not independently verified"`
