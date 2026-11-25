# Registry schema and identity rules

All examples in this bundle are **SYNTHETIC — NOT A SCIENTIFIC CLAIM**.

## Minimal structure

```json
{
  "entities": [{
    "canonical_id": "hgnc:TP53",
    "entity_kind": "gene",
    "species": "Homo sapiens",
    "gene_symbol": "TP53",
    "aliases": ["TP53", "p53"],
    "alias_policies": {"p53": "context_required"},
    "source_locator": {"document": "curated-source-id", "locator": "record or exact page/table"}
  }],
  "interactions": [{"source": "existing-id", "target": "existing-id"}]
}
```

`canonical_id` is the permanent join key. It must be unique and match `[A-Za-z][A-Za-z0-9_.:-]*`. Do not use display text as identity. `entity_kind` is exactly one of `gene`, `protein`, `complex`, `family`, `receptor`, `cell_type`, or `small_molecule`.

Allowed species are Homo sapiens, Mus musculus, Rattus norvegicus, Danio rerio, Drosophila melanogaster, and Saccharomyces cerevisiae. `not_applicable` is reserved for small molecules. This explicit allow-list is a validation contract, not a claim that no other species exists; extend code deliberately for another curated corpus.

- Genes require `gene_symbol` and prohibit `protein_name`. Human symbols are uppercase and SVG labels are italic; e.g. human *TP53* is separate from upright TP53 protein. Mouse gene symbols use sentence case, e.g. *Trp53*, and remain mouse-specific records.
- Proteins and receptors require `protein_name`, prohibit `gene_symbol`, and render upright.
- Complexes and families require at least two distinct `members`, each a canonical ID already present. Members are references, never aliases or merged records. Other kinds cannot carry members.
- Every entity needs `source_locator.document` and `source_locator.locator`. The locator points to the curated assertion; it does not prove truth by itself.
- Optional `layout` `{x,y,w,h}` controls only geometry. The style, typography, visible kind, ID, species, and member panel always come from registry semantics.

## Alias normalization and collision policy

Each entity must have a nonempty-string `aliases` list. Matching uses Unicode NFKC, trimmed/collapsed whitespace, then Unicode case folding. A duplicate alias within one record is a warning. The same normalized alias on different canonical records is an `ALIAS_COLLISION` error by default.

To permit controlled polysemy, **every** colliding record must declare the same raw alias or normalized alias key in `alias_policies` with value `context_required`. This downgrades the registry collision to a warning but does not resolve any mention. A mention then requires enough exact `species` and/or `entity_kind` context to leave exactly one candidate:

```json
{"surface": "p53", "species": "Homo sapiens", "entity_kind": "protein"}
```

Zero candidates is `UNKNOWN_MENTION`; multiple candidates is `AMBIGUOUS_MENTION`. Both are errors. The software never picks the first candidate. A gene/protein distinction, cross-species homonym, and unrelated shared abbreviation therefore stay visible.

## Endpoint audit

For every `interactions[]` item, `source` and `target` must exist. Complex/family `members` are also checked. Missing endpoints are listed in `registry-audit.json.unknown_endpoints`. These generic interaction endpoints do not define process semantics; this Skill audits identity references only.

## Artifacts

`registry-audit.json` holds issues, collisions, unknown endpoints, resolution outcomes, and normalization policy. `content-map.json` joins SVG element IDs to canonical IDs, kind, species, typography, aliases, members, and source locators. The audit can pass with context-required warnings only if all mentions resolve. No successful audit certifies scientific accuracy.
