# Task (synthetic minimal example)

The case PDF is a scanned article whose OCR text layer (already extracted to
`inputs/raw_ocr.txt`, three pages separated by form feeds) shows typical OCR
confusion errors. Run the ocr-rescue-postprocess pipeline:

1. `confusion_scan.py` — detect confusion candidates (no edits).
2. `postcorrect.py` — apply only high-confidence, lexicon-plausible edits;
   defer medium/low to the review list; mark garbage as `[unreadable]`.
3. `ocr_qc.py` — before/after suspicious-token QC and `result.json`.

Fill every field of the `output_contract` in `inputs/case.json`. Do not guess
low-confidence text. See `README.md` for the exact commands.

DISCLAIMER: this case is synthetic; the "article" text was written by hand
with planted errors for demonstration purposes.
