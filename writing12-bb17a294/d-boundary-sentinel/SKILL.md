---
name: boundary-sentinel
description: Academic translation & bilingual writing (EN↔ZH) guarded by a semantic-boundary ledger and citation-preservation audit. Extracts every negation, hedge, causal-strength verb, quantifier, attribution and citation marker from the source, then audits the translation so no qualifier is dropped, no claim is strengthened or weakened, no citation is lost, and nothing the author did not say is added (边界清 + 引用保留).
---

# Boundary Sentinel — 学术翻译与双语写作（语义边界与引用守护）

## Purpose

Translate academic material (EN↔ZH) while preserving its **semantic boundary
(语义边界)**: every negation, hedge, causal-strength verb, quantifier,
attribution and citation marker is extracted into a machine-readable
**boundary ledger (边界台账)**, and the translation is audited against that
ledger. The guarantee this skill pursues:

- no qualifier dropped (限定词不丢),
- no claim strengthened or weakened (论断强度不漂移),
- no citation lost, duplicated, reordered or fabricated (引用不丢、不增、不乱序),
- nothing the author did not say is added (不添油加醋); unavoidable
  translator additions are bracketed translator notes (译者注).

Numbers, terminology and sentence alignment are checked only as one-line
mentions inside the change log — this skill deliberately does NOT duplicate
fact-ledger / termbase / alignment machinery.

## Triggers

Use this skill when the task involves: academic paper/abstract translation,
EN↔ZH bilingual writing of research text, 学术翻译, 双语写作, translation
with citations/references, or any request mentioning 边界 / 引用保留 /
semantic fidelity of hedged scientific claims.

## Case workflow

1. **Intake (读取案件)** — Read `/input/case.json` and `/input/task.md`
   (and `environment/resources.yaml` if present). Record the real `case_id`,
   requested deliverables, language direction, and EVERY field of the actual
   `output_contract`. Read the actual material files; a PDF has no
   pre-extracted answer layer — extract it yourself (`pdftotext` is
   available). Never assume schemas or content.
2. **Boundary-marker extraction (边界标记抽取)** — Run
   `scripts/extract_markers.py` on the source text to produce
   `boundary_ledger.jsonl` (one record per marker-bearing sentence: id
   B0001…, text, negation / hedge / causal_strength / quantifier /
   attribution / citation lists). The extractor is regex-based and
   recall-oriented: skim the flagged sentences yourself and add any marker
   it missed to your working notes.
3. **Translation (翻译)** — Translate the material yourself, sentence by
   sentence, consulting the ledger. Obey the boundary rules in
   `references/method.md`: hedge→hedge mapping table, causal strength
   classes (strong/moderate/weak), `only`→仅/只, et al. handling, and
   bracketed translator notes `[译者注: …]` for any unavoidable addition.
4. **Boundary + citation audit (边界与引用审计)** — Run
   `scripts/audit_boundary.py` (→ `boundary_audit.json`, non-zero exit on
   errors) and `scripts/citation_check.py` (→ `citation_report.json`,
   non-zero exit on errors). Resolve every `error` finding by fixing the
   translation; re-run until clean or the finding is consciously queued.
5. **Human-confirmation queue ([待确认] 队列)** — Anything that cannot be
   resolved deterministically (ambiguous source, heuristic uncertainty,
   justified deviation from the mapping table) is written into the
   deliverable as a `[待确认]` item AND logged in `change_log.md` with the
   source sentence, the issue, and the provisional decision.
6. **Deliver (交付)** — Write the case-requested deliverable(s),
   `boundary_ledger.jsonl`, `boundary_audit.json`, `citation_report.json`,
   `change_log.md`, and `result.json` to `/app/output` (see Runtime
   contract and `references/output_contract.md`).

## Invocation

```bash
# 1. extract the boundary ledger from the English source
python3 scripts/extract_markers.py source.txt -o boundary_ledger.jsonl

# 2. (agent writes the translation)

# 3. audit boundary preservation (exit != 0 on errors)
python3 scripts/audit_boundary.py boundary_ledger.jsonl translation_zh.md \
    -o boundary_audit.json

# 4. audit citation preservation (exit != 0 on errors)
python3 scripts/citation_check.py source.txt translation_zh.md \
    -o citation_report.json
```

For ZH→EN directions, swap roles: run the extractor on the English
*translation* as a proxy ledger and manually verify each Chinese marker has
an English counterpart; the same boundary rules and [待确认] queue apply.

## Inputs / outputs

- **Inputs**: case files under `/input/`; the source research material
  (txt/md/pdf — extract PDFs with `pdftotext`); language direction.
- **Outputs** (in `/app/output` unless the case says otherwise):
  the case-requested deliverable(s); `boundary_ledger.jsonl`;
  `boundary_audit.json`; `citation_report.json`; `change_log.md`;
  `result.json`. Editable Office/slide/diagram artifacts additionally need
  real PDF/PNG previews.

## Exception handling

- **Audit errors** → fix the translation and re-run; if unfixable without
  changing author intent, keep the faithful rendering and queue `[待确认]`.
- **Missing/unreadable input** → state exactly what is missing in
  `result.json` (honest `status: "partial"`), never fabricate content.
- **Heuristic failure** (splitter/regex misfires) → note it in
  `change_log.md`, resolve manually; the scripts flag candidates for human
  check, they do not prove correctness.
- **Budget pressure** → deterministic scripts run early; save per-section;
  a partial `result.json` listing precisely what is missing and why is
  always acceptable, fabrication never is.

## Runtime contract

1. **Read the case first.** Open `/input/case.json` and `/input/task.md`
   (and `environment/resources.yaml` if present) before anything else.
   Record the actual `case_id`, the requested deliverables, the language
   direction, and EVERY field of the real `output_contract` — never assume
   its schema. Read the actual material files; a PDF has no pre-extracted
   answer layer — extract it yourself (`pdftotext` available).
2. **Workspace & early save.** Create `/app/work` and `/app/output`. Save a
   valid EARLY partial `/app/output/result.json` before any long work, and
   update it atomically after each stage. Budget: 64 model requests /
   900 s — run the deterministic scripts early, save per-section.
3. **Final `/app/output` contents**: the case-requested deliverable(s);
   `boundary_ledger.jsonl`; `boundary_audit.json`; `citation_report.json`;
   `change_log.md` (including every resolved AND every acknowledged/queued
   finding); and `result.json` containing the real `case_id`, ALL actual
   `output_contract` fields, an honest status, sources, uncertainty (every
   `[待确认]` item), and change records. Editable Office/slide/diagram
   artifacts also need real PDF/PNG previews.
4. **Honesty.** A partial result states exactly what is missing and why.
   Never fabricate translations, citations, reference entries, or findings.

## Bundle map

- `scripts/extract_markers.py` — source → `boundary_ledger.jsonl`
- `scripts/audit_boundary.py` — ledger + translation → `boundary_audit.json`
- `scripts/citation_check.py` — source + translation → `citation_report.json`
- `scripts/cite_patterns.py` — shared citation regexes (imported by the above)
- `references/method.md` — boundary rules, hedge mapping table, [待确认] workflow
- `references/output_contract.md` — how to fill `/app/output/result.json`
- `examples/synthetic/` — small fully synthetic worked example (合成示例)
