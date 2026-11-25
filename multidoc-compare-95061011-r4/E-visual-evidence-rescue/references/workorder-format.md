# Enriched workorder format

The validator consumes a JSON object with `documents`, `matrix_fields`, honest `status`, `sources`, `uncertainty`, and `change_records`. Each document has an exact `source_document_id`, source `path`, `regions`, and `extractions`. Relative document paths resolve under `--input-root` during ingestion.

Minimal structural sketch (replace placeholders; do not invent unavailable IDs or values):

```json
{
  "status": "partial",
  "matrix_fields": ["removal_efficiency"],
  "documents": [{
    "source_document_id": "DOC_EXACT",
    "path": "documents/source.pdf",
    "regions": [
      {
        "source_document_id": "DOC_EXACT",
        "page": 3,
        "region_type": "caption",
        "region_id": "DOC_EXACT:caption-001",
        "paragraph_id": "DOC_EXACT:caption-001",
        "text": "Exact caption text"
      },
      {
        "source_document_id": "DOC_EXACT",
        "page": 3,
        "region_type": "table_row",
        "region_id": "DOC_EXACT:table-001-row-001",
        "paragraph_id": "DOC_EXACT:caption-001",
        "text": "Exact row text",
        "table": {
          "headers": ["Material", "Removal (%)"],
          "header_paths": [["Material"], ["Removal (%)"]],
          "units": {"Removal (%)": "%"},
          "sample_splits": {},
          "header_text": "Material  Removal (%)"
        },
        "cells": [
          {"header":"Material", "header_path":["Material"], "value":"M1", "source_value":"M1", "units":null, "sample_split":null, "carried_from_previous_row":false},
          {"header":"Removal (%)", "header_path":["Removal (%)"], "value":"82", "source_value":"82", "units":"%", "sample_split":null, "carried_from_previous_row":false}
        ],
        "multirow_context": {}
      }
    ],
    "extractions": [{
      "record_id": "DOC_EXACT:r001",
      "field_id": "removal_efficiency",
      "source_document_id": "DOC_EXACT",
      "paragraph_id": "DOC_EXACT:caption-001",
      "region_id": "DOC_EXACT:table-001-row-001",
      "status": "reported",
      "value": 82,
      "task": "batch_adsorption",
      "metric": "removal_efficiency",
      "units": "%",
      "material": "M1",
      "pollutant": "methyl_orange",
      "budget": "50 mg",
      "dataset_id": "dataset_A",
      "dye_id": "methyl_orange"
    }]
  }],
  "sources": [],
  "uncertainty": [],
  "change_records": []
}
```

## Region shapes

- `prose`: `region_id` is null; stable `paragraph_id` locates the text. An extraction with null `region_id` resolves to exactly one prose region with the same document/paragraph ID.
- `table_row`: non-null `region_id`, context `paragraph_id`, header/cell structure above.
- `figure_panel`: non-null `region_id`, context/caption `paragraph_id`, nonempty `panel_labels`, exact visible region text.
- `caption`: non-null `region_id` and `paragraph_id`; valid for qualitative context and explicitly nonnumeric `not_reported` reasons, invalid as support for numeric curve values.

Every extraction has a globally unique `record_id`. Required comparison qualifiers remain present even for `not_reported` and `noncomparable`, using `not_reported` where the qualifier itself is absent. Quantitative values cannot use missing/unknown/not-reported qualifiers.

`derived` records additionally require numeric `value`, `derivation`, and `derived_from`. `read_off_figure` requires a null exact `value`, estimate/range, `uncertainty.note`, and nonempty `visual_inspection.paths` plus method/notes. See the valid fictional `example/input/comparison-workorder.json` for all region types and statuses.

## Result rendering

`case.json.output_contract` can be an object, a string list, or a descriptor list using `name`, `field`, `field_id`, `key`, or `id`. `render` always writes exact `case_id` and all contract keys. Known fields (`comparison_matrix`, `source_region_ledger`, `status`, `sources`, `uncertainty`, `change_records`, `quality_summary`) have renderer defaults. Supply custom values under top-level `result_fields` keyed by exact contract name; unsupported custom fields remain null and trigger a warning rather than fabricated data.

The renderer adds `artifacts`, `visual_inspection_index`, and validation counts. Workorder `sources`, `uncertainty`, and `change_records` should identify source regions and actual generated text/image paths. The runtime example's figure source is text only and explicitly disclaims binary/OCR inspection.
