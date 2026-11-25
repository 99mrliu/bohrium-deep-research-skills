# Scientific evidence and original-figure comparison

The source paper and supplied original figures govern factual content. The synthetic example never governs an actual case.

## Original paper / figure03 protocol

1. Read actual `task.md`, `case.json`, PDF text and captions. Record source version or supplied filename; do not invent bibliographic metadata.
2. Locate the original `figure03` (including filename/caption variants such as Fig. 3 or Figure 3). Render it at a scale where line endings and small labels are visible. Inspect the original image, not merely an OCR text layer.
3. Make three ledgers before editing: entities, relationships, and numeric/data encodings. Capture exact source labels, page/panel/region, and ambiguity.
4. After rendering the candidate, compare every original entity and every candidate entity in both directions. Explain deliberate omissions/additions. Check quantities, component roles, labels and units.
5. Compare every original connection: source, target, direction, arrowhead/bar, branch/junction, feedback, and sequence. Check every candidate connection back to the original or cited paper text. A visually plausible arrow is not proof.
6. Review biological semantics explicitly: activation/enabling has a terminal arrow; inhibition/blocking has a terminal perpendicular bar. A minus sign, generic arrow, or red color alone is not a substitute. A source that does not establish direction remains unresolved.
7. Inspect chart source columns and rows directly. Preserve numeric values and units. Do not derive pathway entities from chart column names unless the source explicitly supports that interpretation.
8. Record the comparison in sources/change records. Visual/export QC can establish artifact integrity but cannot certify scientific agreement.

## Handling missing or contradictory evidence

- Missing source: produce any independently useful layout shell only if requested, label the limitation, and keep factual nodes/relations empty or unresolved.
- Ambiguous label or interface: retain the source wording, note the ambiguity, and avoid adding an interface.
- Contradictory sources: cite both locators and do not silently choose the convenient one.
- Missing chart column/value: fail the automated mapping or report partial; never replace it with a zero or synthetic number.
- Existing bitmap only: an SVG tracing/reconstruction is a new editable reconstruction, not preservation of original vector bytes.

Every key scientific entity and relation should have a locator. Typography, panel positions, accessible palette, and generic apparatus glyph geometry are design decisions and should be identified as such, not disguised as sourced observations.
