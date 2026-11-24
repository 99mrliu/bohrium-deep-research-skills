# Method — extraction & fidelity rules（上游数据真实性规则）

These rules govern how source facts are extracted, how a translation is
judged against the fact ledger, and how anything uncertain is marked.
The deterministic implementation lives in `scripts/`; this document is the
human-readable contract the agent must follow when translating and when
writing the deliverable mapping.

## 1. Provenance-anchored extraction（溯源锚定抽取）

- Always extract through `scripts/extract_source.py`. Never rely on a
  "pre-extracted answer layer": a supplied PDF is extracted by you, with
  `pdftotext -layout` and form-feed page splitting.
- Every fact carries `page` + `line` + `context` back to `source.txt`.
  If you quote or map anything in the deliverable, cite these anchors.
- If extraction degrades (no pdftotext, empty text layer), say so in
  `result.json` (`status: "partial"`, extraction marked degraded) — never
  invent source text.
- Coverage is verifiable: `extraction_manifest.json` records the method,
  file size, page count, per-page char counts, and a sha256 of
  `source.txt`. A reviewer can re-run extraction and compare.

## 2. Fact ledger discipline（事实台账纪律）

- One JSON object per fact in `facts.jsonl`, stable ids F0001…
- Types: `number`, `percent`, `range`, `year`, `sample_size`,
  `unit_value`, `citation_marker`, `figure_ref`, `table_ref`.
- The ledger is built from the source BEFORE translating. Translate
  against the ledger, not from memory.
- If you notice a source number the script missed (e.g. a spelled-out
  number like "twelve patients"), add it manually as a new ledger line
  with the next free id and a `"note": "manual addition"` field, and
  record this in `change_log.md`.

## 3. Translation fidelity rules（翻译保真规则）

1. **Never round.** 15.0% stays 15.0%, not 15%. 37.0 °C stays 37.0 °C.
2. **Never convert units unless the case explicitly asks.** mg stays mg;
   USD may be rendered 美元 only when the numeric value and magnitude are
   untouched (USD→美元 is a label translation, not a conversion).
3. **Cross-locale number rules.** 万 = ×10⁴, 亿 = ×10⁸; million = ×10⁶,
   billion = ×10⁹. Rewriting 2.5 million as 250万 is allowed but is a
   `normalized` event: it must appear in the audit report and in the
   deliverable mapping. Prefer digit-exact renderings when in doubt.
4. **Percents stay percents.** Writing 15.0% as 0.15 is `altered`.
5. **Ranges keep both endpoints and a connector** (– — - ~ 至 到 to).
   2–6 years → 2–6 年 is fine; dropping an endpoint is `missing`.
6. **Citations travel with the claims.** [12], (Smith, 2020),
   Li et al. (2021) must all appear in the translation, attached to the
   same sentence-level claim as in the source.
7. **Figure/Table references keep their numbers**; the label may be
   translated (Figure 2 → 图 2 counts as `preserved`).
8. **Add nothing.** Any number in the translation with no source
   counterpart is flagged `added` by the audit; each must be justified in
   the change log or removed.

## 4. Verdict semantics（判定语义）

- `preserved` — verbatim, or digit-exact rewrite (thousand separators
  added/removed, whitespace changes), label translation of Figure/Table,
  unit label translated (USD→美元, years→年).
- `normalized` — acceptable cross-locale rewrite, always listed:
  万/亿 ↔ million/billion ↔ ×10ⁿ swaps, scientific-notation swaps.
- `missing` — no trace of the fact value in the translation.
- `altered` — heuristic: a translation number of the same digit length
  differs from the fact in exactly one digit (likely mistranscription),
  or a percent written as a fraction. Treat every `altered` as a
  human-confirmation item.
- Exit code: 0 iff zero `missing` and zero `altered`. `normalized` and
  `added` are reported but non-fatal.

## 5. Unverifiable items（不可核验项）

- Anything you cannot verify against the source or against allowed tools
  (e.g. an author name you are unsure how to transliterate, a term whose
  standard Chinese rendering you cannot confirm) is marked inline as
  `[待确认]` in the deliverable AND listed in `result.json`'s uncertainty
  list AND in `change_log.md` as a human-confirmation item.
- Never silently guess. A marked `[待确认]` is a success of the process;
  an unmarked guess is a failure.

## 6. Provenance in the deliverable mapping（交付物中的溯源映射）

The fact & source mapping delivered with the translation must let a
reviewer trace every number, unit, citation, figure and table back to the
source. Recommended: a table with columns
`fact id | type | source value (raw) | source page/line | translation rendering | translation location | verdict`.
Generate it from `facts.jsonl` + `audit_report.json` — do not retype
values by hand.
