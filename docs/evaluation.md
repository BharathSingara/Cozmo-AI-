# Independent evaluation protocol (NOT YET COMPLETED)

The workbook `data/ground_truth_and_results_template.xlsx` has 60 numbered blank book rows, 20 measurement rows, 15 pricing rows, 8 non-book rows, 10 second-country rows, and one room sheet. **Blank cells are intentionally not test results.** Film with permission and measure independently of the agent. Enter raw observed values in the workbook. Export/import book truth as a CSV for `scripts.evaluate` with columns: `kind,detected,legible,title_correct,pred_title,confidence,true_height_cm,true_thickness_cm,pred_height_cm,pred_thickness_cm,verified_price,pred_price,true_category,pred_category`.

Sample size denominators: book count = every independently counted book, including unreadables/flat/stacked; title = all human-legible spine titles; confidently wrong = incorrect titles among predictions with identification confidence ≥0.80; spine measurements = all 20 preselected independently measured books, missing predictions count as failures; pricing = 15 independently priced book listings, missing predictions fail; nonbooks = all 8+ pre-registered objects, missed categories fail. Floor and wall percentage errors compare to tape-measured dimensions. True floor/wall areas are not inferred from model predictions. Record actual packet timestamp delay, without including camera capture time. Do not claim accuracy from this repository's synthetic integration image.

Example:
```
python -m scripts.evaluate --truth data/your_real_ground_truth.csv --room-json data/your_real_room.json --out data/real_evaluation.json
```

For book-count error, supply `predicted_book_count` in the `--room-json` input. This must include *every* active predicted instance, even unmatched false positives. The evaluator leaves count accuracy **not evaluated** if this value is missing. Maintain a detection-to-ground-truth ID mapping to diagnose both false positives and false negatives.

The actual 60-book study, 10 live second-country prices, first-person unedited video, and before/after measured improvement cannot be generated without the real room/evidence and live market service credentials.
