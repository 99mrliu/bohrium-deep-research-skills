# expected_output.md — what `run_example.sh` produces (合成示例 / synthetic demo)

Everything below is a **synthetic example**: fixture case `synthetic-demo-005`,
paper title contains SYNTHETIC, deck title starts "SYNTHETIC EXAMPLE — ",
`result.json` keeps `"synthetic_example": true`. Numbers are invented demo data.

A successful run exits 0 and ends with `RUN EXAMPLE COMPLETE — exit 0`.

## Artifacts under `examples/work/app-output/`

| Artifact | What it proves |
|---|---|
| `presentation.pptx` | The build stage really produced an editable OOXML deck (3 slides + 3 notes parts), and the build gate's structural checks (valid zip, text on every slide, no TODO/Lorem, count == plan) ran against it. |
| `result.json` | The watchdog kept a valid honest result at every point: written BEFORE real work with `status: "partial"`, advanced per stage, finalized `"success"` only because all three gates PASS. Keeps `case_id: "synthetic-demo-005"`, all six output_contract fields, `"synthetic_example": true`, and an honest exception: `soffice unavailable: PDF export and previews not produced; deck delivered as .pptx only` (on machines without soffice). |
| `gate-plan.json`, `gate-build.json`, `gate-render.json` | Each stage's machine-checked checklist with per-check detail and `verdict: "PASS"`. The render gate's single check is named `renderer-absent` with `ok: true` and an explanatory detail when soffice is missing — an honest degradation, not a hidden failure. |
| `journal.jsonl` | 6-entry append-only hash chain: entry 0 pins sha256 of all 3 input files + tool versions; later entries pin the plan, the built pptx and the gate reports. Re-hash every entry and the linkage holds (`journal: VERIFY OK — 6 entries, chain intact`). |
| `delivery_manifest.json` | sha256 + byte size of every payload artifact, `journal_hash_chain_valid: true`, all gate verdicts. Independently reproducible with `shasum -a 256`. |
| `RUN_REPORT.md` | Human-readable audit: tool-version table (soffice honestly "NOT AVAILABLE"), journal timeline (seq/kind/note/hash prefix), gate verdicts, artifact hashes, honest notes. |

(On a machine WITH soffice, `presentation.pdf` and `previews/*.png` also appear
and the render gate checks page count == slide count instead of recording
`renderer-absent`.)

## Key assertion lines during the run

```
ASSERT ok: result.json exists IMMEDIATELY with honest status=partial
gate plan: PASS ... / gate build: PASS ... / gate render: PASS (renderer-absent detail)
replay --check: ALL OK
watchdog: finalized status=success
```

## Negative demo (by design — expected non-zero exits, verified by the script)

The script copies the whole tree to `examples/work/tamper-demo/`, flips ONE byte
in the copied `presentation.pptx`, then requires both detectors to exit 1.
Actual output from a real run (hash prefix varies per run):

```
flipped one byte in .../tamper-demo/app-output/presentation.pptx
journal: VERIFY FAILED — tampering detected
entry seq=3 kind=command: tampered :: file-tampered:app-output/presentation.pptx
replay --check: TAMPERED artifact presentation.pptx — recorded sha256 4f76804e6e9ed58e... does not match current bytes
NEGATIVE DEMO ok: journal verify exit=1, replay --check exit=1 (both non-zero as designed)
original delivery still verifies OK
```

The originals are untouched and re-verify cleanly; only the copy is flagged,
naming the exact artifact (`presentation.pptx`) and the exact journal entry
(seq 3) whose pinned hash no longer matches.
