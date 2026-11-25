# OOXML identity, inheritance, and native diff

## Relationship chain

For each slide the audit follows package relationships, not visual appearance:

```text
ppt/presentation.xml
  -- presentation relationship --> ppt/slides/slideN.xml
  -- slide relationship        --> ppt/slideLayouts/slideLayoutM.xml
  -- layout relationship       --> ppt/slideMasters/slideMasterK.xml
  -- master relationship       --> ppt/theme/themeJ.xml
```

`native_inventory.json` and `native_diff.json` record the actual parts, SHA-256 hashes, and membership of slide IDs and masters in presentation lists. Every final slide must have an existing layout, master, and theme, with its master in the presentation. Slide width/height must equal the base dimensions. Existing layouts, slide masters, notes masters, and themes must retain their original bytes/hashes. When a template has no notes infrastructure, adding speaker notes may create a notes master and its separate notes theme; these additions are explicitly reported as `added_notes_themes`, while every pre-existing theme and every presentation slide chain must remain unchanged.

Using the same color values or copying a theme token file is not enough. Appended slides are created with `python-pptx` from a layout belonging to the actual base presentation, so they inherit native layout/master/theme behavior. Text edits target placeholders, not global typeface replacements.

## Kept-slide identity

A keep operation is an authorization boundary. The engine first saves the edited copy through `python-pptx`, then restores each retained slide XML part and its direct `.rels` part from the immutable base where feasible. Its reported original identity hash covers those two part hashes. Native diff also protects keep-linked direct note/media dependencies and requires the slide→layout→master→theme part chain to remain unchanged.

This means “byte-for-byte where feasible” is measured at the meaningful slide parts, not inferred from a rendered screenshot. If the identity or protected dependency changes, native diff fails. The original input file is never overwritten.

## Allowed changes and reports

Expected changed parts include presentation order/relationships, explicitly edited slide XML/relationships, notes for edited/appended slides, newly added slide parts and relationships, document properties/content types, new media, and explicitly removed slide-related parts. Kept dependencies, masters, layouts, and theme are not broadly allowlisted. The report separately lists:

- `changed_parts`, `added_parts`, `removed_parts`;
- `allowed_changed_parts` and `unauthorized_changed_parts`;
- `kept_slides` with original/final identity and chain checks;
- `dimensions_same`, `theme_untouched`, `layouts_untouched`, `masters_untouched`, `notes_masters_untouched`, and `added_notes_themes`;
- `inheritance_chain_failures`;
- `new_media` and `notes_changes`;
- final native relationship/membership audit.

Do not require the whole PPTX ZIP to be deterministic. ZIP entry timestamps, compression choices, package-level relationship renumbering, and generated properties may differ without changing slide identity. Conversely, a stable ZIP hash alone would not prove keep semantics; inspect the specific parts and chains.

## Practical limitations

python-pptx does not preserve every possible vendor extension during arbitrary edits. The transaction engine therefore fails closed on unauthorized observed changes rather than declaring unsupported markup safe. Existing-slide layout swapping is rejected because relationship-safe layout replacement requires more than assigning a layout name. Keep-slide identity covers the slide XML and direct relationships; it is not a promise that the entire ZIP or all application metadata is immutable. Notes/media changes are reported separately so reviewers can inspect them.
