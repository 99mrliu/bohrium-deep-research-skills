# Primary source inspection and semantic comparison

## Required reading order for biological figure03 cases

1. Read the actual case/task and locate the original source artifact. Verify which file is really figure03 from document structure, nearby caption, and panel labels; do not assume a directory name is enough.
2. Open/render the actual primary figure03 and inspect it visually. Read the **complete figure03 caption** and methods passages governing the shown assay/mechanism. PDF text extraction alone can miss line endings, blunt bars, compartments, and direction.
3. Create a source inventory with path, source version if supplied, figure/page/panel/method locator, availability, and SHA-256 when readable. Do not invent bibliographic metadata.
4. Transcribe depicted topology before drawing: node label/kind/compartment, exact directed relation and regulatory sign, order/phase, feedback, measurement, and any supplied chart mapping. Keep ambiguities explicit.
5. Build the graph only from supported propositions. If figure03, caption, or methods are absent/unreadable, final status remains `partial`; do not replace them with generic domain knowledge.
6. Populate `source_review` only after actual inspection. Its `status: inspected` is an agent attestation, not something the renderer can independently prove. Include actual paths and locators. In an official biological task `primary_biological_source.required` is true.
7. Populate `source_semantics` with original required nodes and edges. These are a semantic extraction of the actual source, not a hidden answer or pixel coordinate list. IDs may be assigned for traceability but must then remain stable.

## Comparison target

Compare final rendered SVG/PNG to original figure03 using:

- node identity, required-node inclusion, kind, and compartment;
- interaction kind, source endpoint, target endpoint, and direction;
- activation versus inhibition versus catalysis versus material flow;
- explicit feedback and phase order;
- branch/join membership and conditions;
- measured property, CSV headers, series names, actual row values, and units;
- uncertainties and deliberate, source-supported changes.

Do **not** require matching coordinates, colors, font sizes, canvas ratio, node shapes, or general decorative style. A compact final layout is valid if all semantic relationships are preserved and readable. Conversely, pixel similarity does not excuse a reversed edge or an invented mechanism.

`source_comparison.json` reports `match`, `mismatch`, or `not_verified`. Mismatches are semantic errors. A deliberate correction requires evidence and a `change_records` entry; otherwise preserve the original relationship. The software compares the transcription to the final graph, while the agent must perform the actual visual primary-source comparison and rendered PNG inspection. Do not claim that an automated JSON comparison alone has visually inspected a paper.

## Evidence conflicts

Retain the original artifact unchanged. Note each conflict with locators and avoid silently choosing a biologically convenient interpretation. If the final workorder explicitly requests a change, record the instruction and supporting source separately from original-source semantics. If neither source supports a relation, omit it and explain the omission as uncertainty/missing evidence rather than proving biological absence.
