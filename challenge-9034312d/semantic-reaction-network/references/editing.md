# Source-preserving SVG edit instructions

When asked to edit an existing scientific SVG, the original SVG is the primary editable source. Do not run `srn.py` over it to regenerate its layout. Keep an untouched source copy, identify the exact existing element ID and literal XML fragment, and use `patch_svg.py`.

## Instruction format

```json
{
  "target_id": "existing-group-or-element-id",
  "expected_old": "<text class=\"small\">Old source label</text>",
  "replacement": "<text class=\"small\">Evidence-backed new label</text>",
  "expected_style_unchanged": true
}
```

`expected_old` must be an exact UTF-8 fragment occurring exactly once. The patch is rejected if the target ID is absent, parser finds duplicate IDs, XML becomes invalid, any ID is added/removed, the fragment lies outside the target subtree, or an unmodified ID-bearing element changes. Target an existing group ID when changing a child: ancestor subtree serialization may differ, but the tool verifies that every non-target element's own attributes/styles are unchanged and rejects edits outside the target/its ancestors. This tool supports targeted replacement, not broad document normalization.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/patch_svg.py \
  --svg /app/work/original.svg \
  --instruction /app/work/edit-instruction.json \
  --output /app/output/edited.svg \
  --audit /app/output/edit-audit.json
```

The audit records source/output hashes, target ID, method, and preservation checks. Add a result `change_records` item identifying original source, target ID, scientific reason, source refs, and audit path. Preserve unmodified IDs and style attribute values. Do not use global find/replace, redraw via a layout engine, rasterize/vectorize, or rewrite unrelated namespaces/formatting.

For complex inserts/deletes, perform a series of exact anchored patches and extend the audit to account for intentional ID changes; never misreport them as unchanged. Render and compare final semantic topology against original figure03/caption/methods. A successful byte patch alone is not scientific validation.
