# ppt-evidence-fidelity-gate

Quote-gated, machine-audited evidence fidelity for paper→academic-PPT
conversion (Bohrium Playground challenge `ppt-c7b80f0d`, bundle B).

The skill turns "paper PDF → slide deck" into a gated pipeline: an evidence
index is extracted from the actual PDF, every factual slide bullet must carry
a verbatim quote from the extracted text, and a deterministic auditor parses
the finished `.pptx` and blocks delivery until every number, unit,
figure/table citation and quote checks out (or is explicitly dispositioned).

## Install

Copy this directory to the harness skill location:

```
/skills/weekly-skill/
  SKILL.md  README.md  GITHUB_URL.txt
  scripts/{extract_evidence,check_plan,audit_deck,make_result}.py
  references/{quote_gate_rules,plan_format}.md
  examples/minimal_example.md
```

No build step; all scripts are executable Python 3.

## Dependencies

| component | requirement |
|---|---|
| all scripts | Python ≥ 3.8, **standard library only** |
| `extract_evidence.py` | poppler `pdftotext` and `pdftoppm` on `PATH` (harness: pdf-text-tool / pdf-render-tool); clear error + exit 2 if missing |
| deck building (agent side) | `python-pptx` if available, else stdlib writer / office-renderer |
| preview rendering | LibreOffice `soffice` (office-renderer), `pdftoppm` |
| fallbacks | ocr-tool for scanned/encrypted PDFs; `fc-list` for fonts |

Developed/tested with poppler 25.x and Python 3.12; scripts pin no versions.

## Usage

See `SKILL.md` for the full protocol. Short form:

```bash
python3 scripts/extract_evidence.py --pdf paper.pdf --outdir /app/work   # PASS 1
# write /app/work/slide_plan.json per references/plan_format.md          # PASS 2
python3 scripts/check_plan.py --plan /app/work/slide_plan.json \
    --index /app/work/evidence_index.json --paper /app/work/paper.txt    # gate 1
# build deck.pptx respecting the organizer template                      # BUILD
python3 scripts/audit_deck.py --deck /app/output/deck.pptx \
    --index /app/work/evidence_index.json --paper /app/work/paper.txt \
    --report /app/output/audit_report.json --plan /app/work/slide_plan.json  # gate 2
python3 scripts/make_result.py --case /input/case.json \
    --out /app/output/result.json --status complete --note "final"
```

Exit codes everywhere: `0` pass/success, `1` validation failures, `2` bad
inputs/environment. `audit_deck.py` accepts `--dispositions dispositions.json`
to resolve findings with documented reasons.

## Limitations

- Caption/section/fact-pool extraction is regex-based (marked
  `heuristic: true`); multi-column layouts and image-only captions can
  confuse it — visually confirm on the rendered page PNGs.
- Number matching is literal (float + normalized unit). It catches mutated
  values/units but not paraphrase-level distortions; the claim-strength
  taxonomy in `references/quote_gate_rules.md` covers those by discipline.
- The auditor cannot tell this paper's results from cited prior work; the
  others'-results rule is agent-enforced (citation-marker check).
- Bare integers ≤ 20 and years 1900–2099 are ignored as benign (documented in
  the audit report heuristics field).
- Scanned PDFs need an OCR pass before extraction; encrypted PDFs may fail.

## Maintenance

- Keep the number/unit regex tables in `extract_evidence.py`,
  `check_plan.py`, and `audit_deck.py` in sync when adding units (they are
  intentionally duplicated so each script stays stdlib-standalone).
- After changing any regex, re-run the smoke flow in
  `examples/minimal_example.md` on a synthetic PDF.
- Issues/extensions: see the GitHub link in `GITHUB_URL.txt`.
