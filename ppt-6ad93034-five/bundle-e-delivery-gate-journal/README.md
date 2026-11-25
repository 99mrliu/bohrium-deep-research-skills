# delivery-gate-journal (bundle e)

Process quality control / delivery governance for academic PPT generation &
editing (学术 PPT 生成与编辑). The bundle's center of gravity is NOT slide
aesthetics — it is making a deck-production run **auditable, tamper-evident
and honest at every interruption**:

- **Stage gates** (`scripts/gate.py`) with machine-checked exit criteria for
  plan → build → render (`references/gate_criteria.md`). FAIL stops the run.
- **Append-only hash-chained run journal** (`scripts/journal.py`) — every entry
  pins the sha256 of its input/output files and links to the previous entry;
  edits to history are detectable (`journal.py verify`).
- **result.json watchdog** (`scripts/watchdog.py`) — a valid, honest
  `result.json` exists BEFORE any real work and after every stage; `success`
  is refused unless all three gates PASS.
- **Replay-verifiable delivery package** (`scripts/replay.py`) —
  `delivery_manifest.json` (sha256 of every artifact) + human-readable
  `RUN_REPORT.md`; `replay.py --check` re-verifies chain and artifacts.

The bundled `mini_build.py` is deliberately minimal (title + bullets + notes +
footer source line) so the pipeline is real and self-contained; gates and
journal can wrap any other builder unchanged.

## Layout

```
skill/
├── SKILL.md                  # start here (runtime contract + 6-step workflow)
├── GITHUB_URL.txt
├── scripts/                  # journal.py gate.py watchdog.py replay.py mini_build.py pdf_text.py
├── references/               # gate_criteria.md, journal_format.md
└── examples/                 # fully synthetic end-to-end demo + tamper negative demo
```

## Quick start (synthetic demo)

```
cd examples && bash run_example.sh
```

Creates a synthetic fixture paper (SYNTHETIC-marked), runs the full gated
pipeline, then flips one byte in a COPY of the deck and shows the journal and
manifest catching it. See `examples/expected_output.md`.

## Guarantees and limits

- Pure Python stdlib, no network; external tools (`pdftotext`, `pdftoppm`,
  `soffice`, `pdfinfo`) are optional and their absence is recorded honestly.
- The gates verify structure and process, not scientific correctness; plan
  evidence quotes must be grounded by the agent in the extracted paper text.
