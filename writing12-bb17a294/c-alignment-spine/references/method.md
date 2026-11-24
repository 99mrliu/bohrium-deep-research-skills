# Method — Bilingual Alignment Spine (对齐主干方法)

This file is the normative spec for the bilingual file format, the
segmentation rules, and the derive-not-retranslate principle. The scripts in
`../scripts/` implement exactly this spec.

## 1. The spine (主干)

`segment_source.py` splits the source text into segments with stable IDs
`⟦S0001⟧, ⟦S0002⟧, ...` assigned in source order. The ordered ID list is
the **spine**. Everything downstream hangs on it:

- the bilingual master (`bilingual.md`) contains exactly one block per ID;
- `check_alignment.py` verifies 1:1 alignment against the spine;
- `derive_target.py` extracts the clean target file from the bilingual
  master **in spine order**.

Three hard rules (绝不合并 / 绝不重排 / 绝不丢弃):

1. **Never merge** two segments. Two ideas in one source paragraph stay in
   one segment (the source defines the granularity, not the translator).
2. **Never reorder** segments. The bilingual file and the derived target
   follow source order exactly.
3. **Never drop or renumber** IDs. If a source segment is intentionally
   omitted from the deliverable (rare; needs case-level justification), the
   omission is recorded in `change_log.md` — the segment still exists in
   the spine and in the bilingual master.

## 2. `source_segments.txt` format

One block per segment, separated by exactly one blank line:

```
⟦S0001⟧ heading
# Original Title

⟦S0002⟧ paragraph
First source paragraph ...
```

- Header line: `⟦Sdddd⟧` + one kind token.
- Kinds: `heading | paragraph | caption | footnote | equation |
  reference_entry | list_item`.
- Lines before the first header that start with `#` are comment lines.
- Humans may edit segment **text** (e.g., to fix a bad OCR/PDF extraction)
  but never IDs, kinds, or order. All edits go in `change_log.md`.

## 3. `bilingual.md` paired-block format (规范格式)

Exactly one block per spine ID, in spine order:

```
⟦S0004⟧ paragraph
> SRC
Academic translation often breaks structural correspondence between
source and target texts. A stable segment spine prevents drift.[^1]

> TGT
学术翻译常常破坏原文与译文之间的结构对应关系。稳定的分段主干可以防止漂移。[^1]

> NOTE
译注（可选）：说明译法选择；NOTE 块不属于译文。
```

Precise rules:

- **ID line**: `⟦Sdddd⟧` optionally followed by a kind token
  (informational only; the checker takes kinds from
  `source_segments.txt`). IDs must match `⟦S\d{4}⟧`. Strict: each spine
  ID exactly once; unknown or duplicated IDs are errors.
- **Marker lines**: exactly `> SRC`, `> TGT`, or `> NOTE` (trailing
  whitespace tolerated). `> SRC` comes before `> TGT` within a block.
- **Content lines**: everything after a marker line, up to the next
  marker line or the next ID line. Content is plain markdown — it is
  **not** blockquote-prefixed line by line. Content lines must never
  themselves start with an ID pattern or a marker line.
- **Blank lines** are tolerated anywhere between blocks and around marker
  lines; leading/trailing blank lines inside a block are trimmed.
- **`> NOTE` blocks** (optional, any number per segment, after `> TGT`)
  hold translator notes (译注). They are **not** part of the translation;
  `derive_target.py` ignores them and `check_alignment.py` does not check
  them.
- **Translated additions** (a clarifying sentence the target needs but the
  source lacks) go in a `> NOTE` block, or — if the case requires them in
  the deliverable — appended inside the same segment's `> TGT` block,
  clearly marked (e.g., 【译注】...). They are **never** turned into fake
  new segments with invented IDs.

## 4. How structural elements stay in place (各就其位)

| Element | Rule |
|---|---|
| Headings | The `#` prefix is part of the segment text; TGT keeps the same level (`##` stays `##`). |
| Figures/tables | Caption segments keep their numbers (`Figure 1` → `图 1`). The checker requires every SRC figure/table number to appear in TGT. |
| Equations | `equation` segments keep the math body **byte-identical** after whitespace normalization (whitespace-normalized SRC must be a substring of TGT). Add explanation in `> NOTE`, not in the formula. Display math `$$...$$` / `\[...\]` may span lines and stays one segment. |
| Footnotes | Inline markers `[^1]` stay in their paragraph's TGT; definitions `[^1]: ...` are their own `footnote` segments and keep the same label. |
| Citations | Every citation marker `[12]`, `[3,4]`, `[5-7]` in SRC must appear in TGT with the same multiplicity. |
| References | Each entry in a `References`/`参考文献` section is one `reference_entry` segment. Keep the original entry; append translation in-line (e.g., （...）) only if the case asks for it. |
| Lists | Each list item is one `list_item` segment; keep the bullet/number marker in TGT. |

## 5. Deriving the clean target (派生，不重译)

The deliverable `translation_target.md` is produced **only** by
`derive_target.py`:

```
python3 scripts/derive_target.py bilingual.md \
    --segments source_segments.txt \
    --inventory structure_inventory.json \
    -o translation_target.md --json coverage.json
```

It concatenates the `> TGT` blocks in spine order, strips IDs, keeps
heading markup, and verifies coverage against `structure_inventory.json`
(sections, figure/table numbers, equations, reference entries,
footnotes). It exits non-zero and writes nothing if any segment lacks a
TGT. **Never** retranslate the source to produce the target file; the
bilingual master is the single source of truth. If the target file looks
wrong, fix the `> TGT` block in `bilingual.md` and re-derive.

## 6. Alignment checking

```
python3 scripts/check_alignment.py bilingual.md source_segments.txt \
    --json alignment_report.json
```

Per segment, exactly one verdict: `ok | missing_tgt | missing_src |
marker_mismatch | order_violation`. Non-zero exit on any failure, on
duplicate IDs, or on unknown IDs. Fix and re-run until the status is
`pass` before deriving the target.

## 7. Human post-editing without breaking the spine (人工后编辑)

- Edit **only** inside `> TGT` (or `> SRC`, rarely, to fix extraction
  errors) and `> NOTE` blocks. Never touch ID lines, never add/remove
  blocks, never reorder.
- After every editing session, re-run `check_alignment.py` (cheap,
  deterministic) before continuing.
- If a sentence must move across a segment boundary, move it together
  with a `> NOTE` explaining the move; the segment count and IDs stay
  fixed.
- After post-editing, re-derive `translation_target.md`; do not edit the
  derived file directly (edits there would be lost on the next derive).

## 8. Segmentation heuristics worth knowing

- A "References" / "Bibliography" / "参考文献" heading switches the
  segmenter into references mode; subsequent blocks are
  `reference_entry` until the next heading.
- A single-line block is classified `equation` if it contains math
  markers (`= \ ^ _`) and at most two prose words — a heuristic; check
  `structure_inventory.json` counts after segmenting and fix misclassified
  kinds by hand (kind edits in `source_segments.txt` are allowed; ID
  changes are not).
- HTML comments `<!-- ... -->` in the source are treated as metadata and
  skipped.
