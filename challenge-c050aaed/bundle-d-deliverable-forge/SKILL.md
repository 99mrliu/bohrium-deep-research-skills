---
name: deliverable-forge
description: Compose typed structured notes from reading annotations into evidence-linked, inspectable deliverables (Markdown notebook + standalone HTML index) with quote-level verification and human-edit diff retention. Chinese trigger terms: 笔记结构化, 证据链, 可检视交付, 渲染, 人工改动留痕. Use when extracted PDF annotations or fragments must become auditable notes where every claim carries a verbatim quote proven to occur at the cited page of the cited file.
---

# Deliverable-Forge (下游交付工程)

Turn extracted reading annotations/fragments into **inspectable,
evidence-linked deliverables**: typed structured notes whose every claim
carries a verbatim quote that a script *proves* occurs at the cited page of
the cited file, rendered as a Markdown notebook and a standalone HTML index,
with unified diffs retained for any human/manual edits.

## When to use

- You have `annotations.jsonl` from any extractor and page texts, and must
  deliver a notebook a reviewer can open, click through, and independently
  re-verify.
- You need a hard evidence-chain gate (证据链): no claim ships unless its
  quote is found verbatim at the cited location.
- You need human edits to stay auditable (人工改动留痕) via snapshots/diffs.

## Inputs & runtime contract (evaluation environment)

- Inputs: `/input/case.json`, `/input/task.md`, plus real materials
  (PDFs/texts, and possibly pre-extracted annotations).
- Work under `/app/work`; deliverables under `/app/output`.
- `/app/output/result.json` **MUST** contain the original `case_id` and every
  field named by the case's `output_contract` — read the contract dynamically
  from `/input/case.json`; never hardcode field names.
- Honesty: write a **partial `result.json` EARLY** (right after reading the
  case), then improve it in place. `status` ∈ {complete, partial, failed}.
  Record sources, uncertainty, `change_records`, and every
  skip/failure/conflict/recovery. Never fabricate content or verification.
- Budget: 64 model requests / 900 s. The scripts are cheap; your reading and
  claim-authoring is the budget consumer.

## Producing sources in the eval env

Scripts operate on `sources/<filekey>/page-NNN.txt` (3-digit zero-padded).
Produce page texts with stdlib probing and honest failure:

```python
import shutil, subprocess, pathlib
out = pathlib.Path("/app/work/sources/mypaper"); out.mkdir(parents=True)
if shutil.which("pdftotext"):
    subprocess.run(["pdftotext", "-layout", pdf, str(out / "all.txt")], check=True)
    # then split all.txt on \f (form feed) into page-001.txt, page-002.txt, ...
else:
    try:
        import fitz  # PyMuPDF, if installed in the env
    except ImportError:
        # honest failure: record in result.json that page texts could not be
        # produced; set status partial; do NOT invent page texts
        raise
```

Write `sources/<filekey>/source.json` with the tool name and per-page sha256
so renders carry provenance. `annotations.jsonl` fields:
`annotation_id, file, page, type, category, color_hex, anchored_text,
contents, author` — from any extractor; a companion field may mark migrated
annotations: **pass it through, never reinterpret it**.

## Workflow (exact commands)

```bash
S=/skills/weekly-skill/scripts
W=/app/work
# 1. Author drafts.jsonl yourself (you read the material; see schema), then:
python3 $S/compose_notes.py --annotations $W/annotations.jsonl \
    --sources-dir $W/sources --drafts $W/drafts.jsonl --out $W/notes.jsonl
# 2. Hard evidence-chain gate (exit 3 unless every claim verified):
python3 $S/verify_claims.py --notes $W/notes.jsonl \
    --sources-dir $W/sources --out $W/claims_report.json
# 3. Render deliverables:
python3 $S/render_deliverables.py --notes $W/notes.jsonl \
    --claims-report $W/claims_report.json --sources-dir $W/sources \
    --out-dir /app/output/deliverables
# 4. After any human/manual edit, retain it:
python3 $S/render_deliverables.py --out-dir /app/output/deliverables --snapshot before-edit
python3 $S/render_deliverables.py --out-dir /app/output/deliverables --snapshot after-edit
python3 $S/render_deliverables.py --out-dir /app/output/deliverables --diff before-edit after-edit
```

Repeat 1–3 until verify exits 0; each loop, update `result.json` in place.

## Outputs

- `notes.jsonl` — normalized typed notes with locators + note↔annotation
  correspondence (per-note `annotation_ids`; annotation→notes in stdout).
- `claims_report.json` — per-claim status, `verified_rate`, `all_verified`.
- `notebook.md` — grouped by note type; claim, quote blocks with locators
  `file — p.N — annotation_id`, tags, status; provenance header (page
  hashes, tool version; `--example` adds a synthetic banner).
- `index.html` — standalone, inline CSS, clickable `#note-<id>` anchors,
  verification summary table, no external resources.
- `manifest.json` — deliverable file list with sha256.
- `change_records/` — snapshots and unified diffs of human edits.

## Failure handling

- Exit codes: 0 success; 2 usage/IO error; 3 validation/verification failure.
- compose exit 3: offenders (note_id + reasons) on stderr; notes.jsonl NOT
  written. Fix drafts, re-run. Common causes: unknown note_type, empty claim,
  unresolvable annotation_id, quote < 8 chars.
- verify exit 3: per-claim `file_missing` / `page_missing` /
  `quote_not_found` with note_id on stderr. Fix the quote (copy verbatim from
  the page text), fix the locator, or drop the claim — then record the
  recovery in `result.json`. Never weaken a quote to force a pass.
- If sources cannot be produced at all, set `status: partial` or `failed`
  with the reason; ship whatever is honestly verifiable.

## Boundaries

- **No annotation extraction** (input is given/produced elsewhere), **no
  version migration**, **no retrieval index/search engine**.
- The agent authors the claims; the scripts only validate / verify / render.
  The notes' intellectual content comes from your reading of the material —
  `excerpt_only` warnings mark notes that are pure excerpts; rewrite them.

## Minimal example

See `examples/` (fully synthetic): fixtures, README with exact commands, and
EXPECTED.md with real observed outputs. Quick smoke run:

```bash
cd examples && head -n 5 drafts.jsonl > /tmp/d5.jsonl
python3 ../scripts/compose_notes.py --annotations annotations.jsonl \
    --sources-dir sources --drafts /tmp/d5.jsonl --out /tmp/notes.jsonl
python3 ../scripts/verify_claims.py --notes /tmp/notes.jsonl \
    --sources-dir sources --out /tmp/claims.json   # exit 0, rate 1.0
```
