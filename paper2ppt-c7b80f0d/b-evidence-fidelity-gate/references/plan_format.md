# slide_plan.json format

Written by the agent in PASS 2; validated by `scripts/check_plan.py` before
deck building; later reused to derive `/app/output/evidence_map.json`.

## Schema

```json
{
  "title": "<deck title>",
  "audience": "<from case.json, if given>",
  "slide_limit": 12,
  "slides": [
    {
      "id": "s1",
      "kind": "title|motivation|method|results|limitations|conclusion|backup",
      "claim": "the single claim this slide makes (one sentence)",
      "bullets": [
        {
          "text": "slide bullet text as it will appear on the deck",
          "quote": "verbatim sentence copied from paper.txt (required when text states a number/unit/method/dataset/conclusion)",
          "locator": {"page": 1, "figure": "1", "table": null, "section": "Abstract"},
          "status": "established|supported|preliminary|inferred|unsupported"
        }
      ],
      "figure_ref": "Figure 1",
      "figure_class": "schematic|data",
      "notes": "speaker notes: transitions, emphasis, backup detail; no new unbacked numbers",
      "evidence": [
        {"quote": "verbatim copy from paper.txt",
         "locator": {"page": 2, "figure": "2"}}
      ]
    }
  ]
}
```

Field rules:

- `slides[]` is required; everything else has a sane default but be explicit.
- `bullets[].quote` — required iff `text` contains a number+unit token, a
  method/dataset name, or a conclusion; must be a whitespace-normalized
  verbatim substring of `paper.txt`. Copy, never retype.
- `bullets[].status` — required, from the five-value taxonomy above.
- `figure_ref` — a `Figure N` / `Table M` string; N must exist in
  `evidence_index.json`. `figure_class` required whenever `figure_ref` is set.
- `notes` — string; number+unit tokens in notes are checked against the paper
  fact pool just like bullets.
- `evidence[]` — slide-level quotes backing the claim; merged into
  `evidence_map.json` at delivery.

## Filled example (ILLUSTRATIVE — not real case output)

```json
{
  "title": "FastConv: Example Walkthrough",
  "slide_limit": 8,
  "slides": [
    {
      "id": "s1",
      "kind": "title",
      "claim": "FastConv trains faster without accuracy loss.",
      "bullets": [],
      "figure_ref": null,
      "figure_class": null,
      "notes": "One-sentence hook; do not repeat the title verbatim.",
      "evidence": []
    },
    {
      "id": "s4",
      "kind": "results",
      "claim": "FastConv reaches 92.3% accuracy on the XYZ dataset.",
      "bullets": [
        {
          "text": "92.3% accuracy on XYZ, matching the baseline",
          "quote": "FastConv achieves an accuracy of 92.3% on the XYZ dataset, matching the baseline.",
          "locator": {"page": 1, "figure": null, "table": "1", "section": "Abstract"},
          "status": "supported"
        },
        {
          "text": "Convergence over 200 epochs (Figure 1, data)",
          "quote": "Figure 1: Convergence of loss over 200 epochs.",
          "locator": {"page": 2, "figure": "1"},
          "status": "supported"
        }
      ],
      "figure_ref": "Figure 1",
      "figure_class": "data",
      "notes": "If asked about variance: paper reports a single run, 200 epochs.",
      "evidence": [
        {"quote": "FastConv achieves an accuracy of 92.3% on the XYZ dataset, matching the baseline.",
         "locator": {"page": 1, "table": "1"}}
      ]
    }
  ]
}
```
