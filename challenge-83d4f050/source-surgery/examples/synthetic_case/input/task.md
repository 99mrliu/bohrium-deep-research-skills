# SYNTHETIC source-surgery task

Canonical runtime root: `/app/case/source-surgery` (must contain `task.md` and `input/case.json`). A case directory itself may instead contain `case.json`, `task.md`, all source files, and `source_surgery/workorder.json`.

1. Read the actual source excerpt, original layered SVG, generated figure03.png, data.csv, and workorder.json. Record source hashes before editing.
2. Run `python3 scripts/source_surgery.py run --case-root /app/case/source-surgery`. Work defaults to `/app/work/source-surgery`, output to `/app/output/source-surgery`.
3. The only allowed edits are those in the work order. No input file may be overwritten. Missing or duplicate IDs must abort the entire operation with non-zero status and no final edited SVG/PNG/PDF.
4. Inspect the actual edited PNG and PDF using native image/PDF reading. Then attest with concrete observations and limitations, for example:

   `python3 scripts/source_surgery.py attest --case-root /app/case/source-surgery --reviewer Agent --observation "Edited response B is readable; unrelated notes remain present." --limitation "Synthetic fixture; font metrics may differ by renderer." --passed`

Before visual attestation the honest status is `partial`; failed visual attestation returns 4. Complete must mean artifact, content mapping, sources, uncertainty, change records, and native visual review are all present.
