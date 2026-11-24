# Artifact contract

What the delivery-side words mean operationally in this skill.

## "Editable artifact"

The evaluator must be able to open the file in the intended application and
continue editing. Concretely:

| Requested | Delivered | Test |
|---|---|---|
| docx | Real OOXML zip: `[Content_Types].xml`, `_rels/.rels`, `word/document.xml`, `word/styles.xml` | unzip lists the members; `document.xml` parses; text runs present |
| Markdown | UTF-8 `.md` with the case's section structure | re-read the file; headings and citation markers intact |
| LaTeX | `.tex` that compiles with the runtime's compiler | compile once; PDF produced without errors |

A renamed file fails this contract: `introduction.md` copied to
`introduction.docx` is a text file with a misleading extension, and an
evaluator opening it in Word gets an error, not a document. `md2docx.py`
exists precisely to avoid that failure mode without external dependencies.

## "Preview"

A rendered artifact a human can inspect without the editing application:
PDF when pdflatex/xelatex/tectonic or matplotlib is available, plain text
otherwise. Rules:

- The preview is generated **from the shipped source**, never maintained
  separately — regenerate after every content edit.
- The preview report names the renderer. When no PDF renderer exists the
  status is `not_verifiable`; that honesty is part of the contract, because a
  claimed-but-absent PDF is worse than a text preview.
- Someone reads the preview. The checklist: all headings present, paragraph
  count matches the source, citation markers (`[n]`) visible, no encoding
  artifacts, no truncated final paragraph.

## "Verified delivery"

Three independent re-openings before the run ends:

1. The editable artifact opens in its real format (unzip/parse for docx,
   compile for tex, re-read for md).
2. The preview matches the artifact's content.
3. `result.json` parses, contains `case_id` identical to the input, and every
   `output_contract` field is populated with real values — measured word
   counts, actual paths, actual change records.

## Word budgets

- Count words on prose: citation markers `[n]` and Markdown syntax excluded.
- Per-part limits (e.g. `max_words_related_work`) apply to the rhetorical
  part wherever it lives in the text, heading-marked or not; heading-based
  accounting is exact, cue-based accounting is labeled heuristic.
- Trimming order when over budget: duplicated background framing first, then
  decorative citations, then connective filler — never the contribution
  evidence or a stated limitation. `word_budget.py` lists the longest
  sentences of the offending part to start from.
