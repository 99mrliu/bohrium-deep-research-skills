---
name: delivery-forge
description: Downstream delivery and rendering engineering for academic translation & bilingual writing (学术翻译与双语写作 EN↔ZH). Turns a bilingual master markdown into reviewer-ready editable artifacts with real PDF/PNG previews, a completeness census against the source structure, and an output-contract validation gate before submission (下游渲染工程 / 过程质量控制).
---

# delivery-forge — 下游交付与渲染工程

## Purpose (定位)

This Skill owns the **last mile** of an academic translation case: once a
bilingual master markdown exists (or has just been produced by you, the
agent), delivery-forge turns it into **reviewer-ready, editable artifacts**
and proves their quality with **process quality gates (过程质量门)**:

1. **Render** — a self-contained bilingual HTML deliverable plus a *real*
   PDF preview and a page-1 PNG preview (`scripts/render_bilingual.py`).
2. **Census** — a completeness census proving the deliverable covers every
   section/figure/table/equation/footnote/reference of the source
   (`scripts/census_coverage.py`).
3. **Contract validation** — proof that `/app/output/result.json` satisfies
   the case's *actual* `output_contract` and honestly reports status
   (`scripts/validate_contract.py`).

**Out of scope (one-line mentions only, machinery lives elsewhere):**
number/unit fidelity is tracked by the fact ledger; term consistency by the
termbase; segment alignment and boundary/scope records by upstream tooling.
This Skill consumes their products (the bilingual master, the structure
inventory) and never rebuilds them.

## Triggers (何时启用)

- A case asks for translation, bilingual writing, or bilingual deliverables
  (EN↔ZH) and expects files a reviewer can open.
- Any request that mentions previews, "reviewer-ready", editable output,
  completeness/coverage checks, or contract/result validation.
- The final packaging stage of the challenge "写作12｜学术翻译与双语写作".

## Full case workflow (全流程)

1. **Intake (读取输入).** Read `/input/case.json` and `/input/task.md`
   (plus `environment/resources.yaml` if present). Record: the actual
   `case_id`, requested deliverables, language direction (EN→ZH / ZH→EN /
   bilingual), and **EVERY field of the real `output_contract`** — never
   assume its schema. Read the actual material files; a PDF has **no
   pre-extracted answer layer** — extract it yourself (`pdftotext` is
   available in the runtime).
2. **Translate → bilingual master (双语主文档).** Produce
   `/app/work/bilingual_master.md` in the documented format (headings +
   paired `⟦S0001⟧` blocks with `> SRC:` / `> TGT:` lines — see
   `references/method.md`). Save per-section so a timeout never loses
   finished sections.
3. **Structure inventory.** Produce `/app/work/structure_inventory.json`
   (counts/identifiers of sections, figures, tables, equations, footnotes,
   reference entries in the SOURCE; schema in `references/method.md`).
4. **Render (渲染交付物).** Run `render_bilingual.py` into `/app/output`:
   bilingual HTML always; PDF + page-1 PNG previews when matplotlib is
   importable (it is declared preinstalled); otherwise an honest `skipped`
   status with the reason in `render_qa_log.json`. Every editable artifact
   (HTML/Office/diagram) must have a real preview — never a fake one.
5. **Census (完整性普查).** Run `census_coverage.py` with the inventory
   against the deliverable markdown. Verdicts `covered|missing` per item;
   non-zero exit on ANY missing item → delivery is **blocked** until fixed.
6. **Contract validation (合同校验).** Run `validate_contract.py` with the
   case file and `/app/output`. It reads the contract field names from the
   case file itself; non-zero exit on any violation → delivery blocked.
7. **Deliver (交付).** Final `/app/output` contains the case-requested
   deliverable(s) + previews, `coverage_report.json`, `contract_check.json`,
   `render_qa_log.json`, `change_log.md`, and a final atomically-updated
   `result.json`.

**Quality-gate order is strict: render → census → contract validate.** A
gate failure blocks delivery, is recorded in `change_log.md`, and (if
unfixable within budget) is reported in `result.json` as
`status: "partial"` with the exact gap named in `uncertainty`.

## Invocation (调用方式)

```bash
# from /app/work (master + inventory already produced)
python3 scripts/render_bilingual.py \
    --master /app/work/bilingual_master.md --outdir /app/output --basename bilingual
python3 scripts/census_coverage.py \
    --inventory /app/work/structure_inventory.json \
    --deliverable /app/work/bilingual_master.md \
    --report /app/output/coverage_report.json
python3 scripts/validate_contract.py \
    --case /input/case.json --outdir /app/output
```

Each script prints a one-line verdict and exits non-zero on failure
(except render, which exits 0 even when previews are honestly skipped).

## Inputs / outputs (输入与输出)

| Input | Produced by | Consumed by |
|---|---|---|
| bilingual master markdown | agent (this case) | render + census |
| `structure_inventory.json` | agent / upstream tooling | census |
| `/input/case.json` | platform | contract validation |

| Output | Notes |
|---|---|
| `bilingual.html` | self-contained, embedded CSS, print-friendly |
| `bilingual.pdf`, `bilingual_page1.png` | real previews; runtime artifacts |
| `render_qa_log.json` | font found, preview status, block counts |
| `coverage_report.json` | per-item verdicts + totals |
| `contract_check.json` | violations, warnings, verdict |
| `change_log.md`, `result.json` | version & boundary records, contract fields |

## Exception handling (异常与诚实降级)

- **matplotlib missing / font missing:** previews skipped or degraded with
  an explicit `font_warning` in the QA log; exit stays 0; never fake a
  preview image.
- **Census finds a missing item:** fix the deliverable (translate the
  missing section/caption/reference), re-run census; if budget runs out,
  deliver `partial` and name the missing item IDs in `uncertainty`.
- **Contract violation:** fix `result.json` / add missing files, re-run;
  if unfixable, `partial` with the violating field named in `uncertainty`.
- **Never fabricate** missing software state, previews, or scientific data.

## Runtime contract (运行时契约)

- First read `/input/case.json` and `/input/task.md` (and
  `environment/resources.yaml` if present); record the actual `case_id`,
  requested deliverables, language direction, and EVERY field of the real
  `output_contract`; never assume its schema. Read actual material files;
  a PDF has no pre-extracted answer layer — extract it yourself
  (`pdftotext` available).
- Create `/app/work` and `/app/output`. Save a valid EARLY partial
  `/app/output/result.json` before long work; update it atomically
  (write temp file → `os.replace`) after each stage.
- Budget: 64 model requests / 900 s — run the deterministic scripts early,
  save per-section while translating.
- Final `/app/output`: the case-requested deliverable(s) with real PDF/PNG
  previews for editable artifacts, `coverage_report.json`,
  `contract_check.json`, `render_qa_log.json`, `change_log.md`, and
  `result.json` carrying `case_id`, all actual `output_contract` fields,
  an honest `status`, `sources`, `uncertainty`, and change records. A
  partial result states exactly what is missing and why. Never fabricate
  missing software state or scientific data.

## Bundle map

- `scripts/render_bilingual.py` — master → HTML + real PDF/PNG previews (+QA log)
- `scripts/census_coverage.py` — structure completeness census
- `scripts/validate_contract.py` — output-contract validator
- `references/method.md` — master format, deliverable matrix, preview & gate policy
- `references/output_contract.md` — how to fill `result.json`
- `examples/synthetic/` — 合成示例 / synthetic end-to-end worked example
