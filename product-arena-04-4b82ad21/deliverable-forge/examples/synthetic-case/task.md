# Task (SYNTHETIC EXAMPLE — interface demonstration only)

Write the **Introduction** of the manuscript described in `material/manuscript-facts.md`, and inside
it a **Related Work** passage that compares prior methods. Use only the bibliography in
`material/references.json` / `material/references.md`; use only facts stated in the fact base for the
present work.

- Audience: reviewers of a methods-oriented computational biology journal.
- Length: Introduction <= 400 words in total, of which Related Work <= 260 words.
- Citations: Vancouver numbered, numbered by first appearance, only from the provided bibliography.
- The Introduction must carry four connected parts: research background, related work, research gap,
  contributions. The gap must follow from limitations of the cited work, not from a generic claim that
  the topic is important.
- Every statement about another work must be traceable to that work's provided text; where only a
  title is available, do not attribute findings to it.
- Every contribution must point at a figure or section of this manuscript.
- Do not invent numbers, datasets or results. Anything the material does not support goes to open items.

Deliver `result.json` following `output_contract` in `case.json`, plus the editable manuscript text.
