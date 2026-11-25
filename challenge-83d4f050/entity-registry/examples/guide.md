# SYNTHETIC examples

**All labels, values, interactions, and source locators in these directories are SYNTHETIC — NOT SCIENTIFIC CLAIMS.** They exercise software behavior only.

- `synthetic/input/case.json`: human TP53 gene and TP53 protein are separate records with italic/upright typography; mouse Trp53 is separate. Human and mouse records share normalized alias `p53` under `context_required`. Mentions supply species and kind and resolve exactly. A complex and family retain member IDs rather than merging them.
- `synthetic-failure/input/case.json`: the same controlled polysemy has a context-free `p53` mention. Three candidates survive, so validation and the process exit must fail rather than guess.

Each input includes a tiny original SVG, a caption, a work order, and explicitly synthetic data. The runner writes exports only for the successful example. Run through `../scripts/entity_registry.py demo --destination <outside-this-bundle>`.
