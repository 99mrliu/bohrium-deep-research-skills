# Transaction semantics and evidence

## Base and accounting

The base PPTX is immutable input. `base_path` and ordered `base_slide_ids` come from `native_inventory.json`, not from filenames guessed by the agent. Original IDs remain stable regardless of removal, appends, or reorder.

Each original ID must occur exactly once in one of:

- `keep`: no authorized modifications; the engine restores and verifies the original slide XML and direct slide relationships after save where feasible.
- `edit`: authorized changes only. `source_slide_id` must equal `id`. Omitted title, bullets, notes, figures, shapes, and layout remain unchanged. Supplying an empty list/string is an explicit change. Existing-slide layout replacement is rejected; preserve native inheritance.
- `remove`: deliberate deletion of this original ID. Removal never happens merely because an ID is absent.

Each `append` has a unique stable ID not in the original ID set and names a real native layout by global `layout_idx` or unambiguous `layout` name. One last `reorder.final_order` explicitly lists all surviving and appended IDs exactly once. Consequently a linear final-deck description still retains original-target semantics.

The fixed task/workorder slide count is checked against surviving operations, not inferred after rendering. Audience and minutes in the plan must match discovered constraints. The runner rejects unknown IDs, duplicate accounting, omitted originals, dangling layouts/placeholders, and final-order omissions.

## Generation versus adaptation

Generate mode starts from the actual template. Existing template slides must be recorded in `example_slide_ids` before they can be removed. If no explicit list exists, prepare records all existing slides on the selected generation template as examples and documents that decision. Non-example originals cannot be silently removed. Appends still use actual template layouts and placeholders.

Edit/adapt mode starts from the actual starting deck. Preserved slides are not rebuilt, restyled, or normalized to a different theme. Only explicitly targeted placeholders/notes/figures change. In both modes, arbitrary global font replacement and lookalike-template creation are outside the transaction model.

## Content operations

- `title`: replace only the title placeholder, optionally selected by `title_placeholder_idx`.
- `bullets`: replace only a native body placeholder; strings or `{text, level}` items are accepted. Use `body_placeholder_idx` to disambiguate.
- `notes`: populate speaker notes. Evidence references and exact quotes are appended to notes for traceability.
- `figures`: aspect-fit existing image files or source-page/extracted-image assets. Optional `placeholder_idx` supplies native geometry. With bullets, the figure defaults to the lower body region; without bullets it may use the whole body region.
- `presentation_metadata`: bypass scientific-evidence requirements only for nonclaim content such as section dividers or agendas. It is not a waiver for a scientific number.

Placeholder `idx` values are checked against actual target slide/layout placeholders. Indices are global across masters in the flattened inventory, so duplicate layout names need not be guessed.

## Evidence semantics

Every edited/new scientific spec needs `evidence`. Each item has:

- `source_id` and one-based `page` from `source_index.json`;
- `quote`, whose whitespace-normalized text must occur on that exact PDF page;
- preferably `quote_id`, matching the extracted line and its source/page;
- a page reference and optionally `section` and/or `figure` for human traceability.

The requirement is source support, not exact slide wording. A supported paraphrase is valid. Conversely, an exact but unrelated quotation does not make a claim true; the agent remains responsible for semantic support. Every numeric token in title/bullets must appear in attached evidence unless the spec is presentation metadata. This deliberately simple check can produce false positives (for example, a figure number supported only in prose); resolve them by attaching the correct quote, not by suppressing validation.

Notes and evidence are not substitutes for reading actual source context. Extracted line spans can split scientific statements, equations, or multi-line captions. Add multiple evidence items if separate clauses or pages support a slide. PDF text extraction cannot prove chart interpretation; inspect the actual figure/page image.

## Discovery contract

Prepare reads explicit material/artifact/workorder path strings recursively, resolves existing paths, and also inventories actual PDFs/PPTX files under the input root. Role hints come from material `role` and context. Structural fallback uses slide/layout/master counts only when roles are absent and records uncertainty. Domain words in a filename are never a role classifier. All relevant discovered PDFs receive page text, line quote IDs, raster page assets, and extractable raster images.
