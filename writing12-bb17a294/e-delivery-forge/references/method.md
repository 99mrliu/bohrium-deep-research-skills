# delivery-forge method — formats, deliverables, previews, gates

(配套中文术语：双语主文档 = bilingual master；完整性普查 = completeness
census；合同校验 = contract validation；诚实降级 = honest degradation.)

## 1. Bilingual master format (双语主文档格式)

The master is UTF-8 markdown with three block kinds:

```markdown
# 一级标题 Heading Level 1
## 二级标题 Heading Level 2

⟦S0001⟧
> SRC: English source sentence(s) of this segment.
> TGT: 本段的中文译文。

⟦S0002⟧
> SRC: Figure 1 shows the two-leg ladder.
> TGT: 图 1 展示了双腿梯结构。
```

Rules:
- **Segment IDs** are `⟦S####⟧` (4+ digits), monotonically increasing, one
  per source paragraph/caption/equation/reference entry. The delimiters
  `⟦ ⟧` (U+27E6/U+27E7) mark machine-parsable block starts.
- Each segment has exactly one `> SRC:` line group and one `> TGT:` line
  group; continuation `>` lines append to SRC. A blank line closes a
  segment.
- ATX headings (`#`..`######`) carry the (possibly already bilingual)
  section titles and are the census anchors for sections.
- HTML comments `<!-- ... -->` are ignored by the renderer.
- Equations keep their source label verbatim, e.g. `ΔE = hν  (1)` — the
  label `(1)` is the census anchor for equations.
- Figure/table captions keep BOTH numberings when bilingual:
  `Figure 1` / `图 1`, `Table 2` / `表 2`.
- In the PDF/PNG preview, segment IDs render as `[S0001]` because `⟦ ⟧`
  are missing from many CJK fonts; the HTML keeps the original glyphs.

## 2. Structure inventory schema (结构清单 schema)

Produced by the agent or upstream tooling from the SOURCE material:

```json
{
  "source_title": "...",
  "sections":  [{"id": "sec1", "heading": "1 Introduction"}],
  "figures":   [{"id": "fig1", "label": "Figure 1", "alt": "图 1"}],
  "tables":    [{"id": "tab1", "label": "Table 1", "alt": "表 1"}],
  "equations": [{"id": "eq1",  "label": "(1)"}],
  "footnotes": [{"id": "fn1",  "marker": "1", "snippet": "first words"}],
  "references":[{"id": "ref1", "first_author": "Zhang", "year": 2021}]
}
```

All category keys optional; empty lists allowed; unknown keys are reported
as warnings, not errors. Matching rules are implemented in
`census_coverage.py` (heading text; `Figure N`/`图 N` label-or-alt with
flexible spacing; literal equation label; footnote snippet-or-marker;
reference = first-author AND year). Comparison is NFKC-normalized and
case-folded so full/half-width forms compare equal.

## 3. Deliverable matrix (交付物矩阵)

| Case request | Produce |
|---|---|
| Pure translation (纯译文) | translated markdown (`deliverable_translation.md`) + bilingual master + HTML + PDF/PNG previews |
| Bilingual deliverable (双语对照) | bilingual master + bilingual HTML (interleaved SRC/TGT) + PDF/PNG previews |
| Tracked-revision request (修订留痕) | all of the above + `change_log.md` with per-stage change records and, when asked, a revision-annotated master (`⟦S0001⟧` blocks carrying `> NOTE:` lines describing each change) |

In every row the census and the contract check run unchanged; the census
target is the deliverable markdown that a reviewer reads.

## 4. Preview policy (预览策略)

- **Every editable artifact** (HTML / Office / diagram source) gets a REAL
  PDF or PNG preview. Previews are **runtime artifacts**: they are rendered
  during the run, their QA is logged as text (`render_qa_log.json`), and
  they are never hand-drawn, renamed placeholders, or copied from elsewhere.
- Preview rendering is deterministic: wrapped lines (46 chars), 34 lines
  per A4 page, fixed colors (SRC blue / TGT dark red), page footer with
  page numbers. No external renderer (no LaTeX, no headless browser).
- **Font discovery (字体发现):** scan common CJK font paths in order —
  macOS `PingFang.ttc`, `STHeiti*.ttc`, `Hiragino Sans GB.ttc`; Linux
  `NotoSansCJK-Regular.ttc/.otf`, `WenQuanYi zenhei/microhei`; Windows
  `msyh.ttc`, `simhei.ttf`. First hit wins and is recorded in the QA log
  (`font.path`, `font.family`).
- **Honest degradation (诚实降级):**
  - No CJK font found → fall back to matplotlib's default font and write an
    explicit `font_warning` into the QA log (CJK may show as tofu boxes).
  - matplotlib not importable → previews are skipped entirely, the reason is
    written into the QA log (`previews.status = "skipped"`), the HTML is
    still produced, and the script exits 0. We never fake a preview.

## 5. Quality-gate order (质量门顺序)

```
render → census → contract validate
```

1. A gate that fails **blocks delivery**.
2. The failure is recorded in `change_log.md` with the gate name and the
   offending item/field IDs.
3. If the failure cannot be fixed within budget, final `result.json` uses
   `status: "partial"` (or `"failed"`) and names the exact gap in
   `uncertainty` — this is the only situation in which contract fields may
   be empty (the validator enforces this rule).
4. After any fix, re-run ALL downstream gates, not only the failed one.
