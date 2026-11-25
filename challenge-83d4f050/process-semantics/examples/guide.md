# SYNTHETIC examples

**All entities, processes, compartments, values, and locators under these directories are SYNTHETIC — NOT SCIENTIFIC CLAIMS.**

- `synthetic/input/case.json`: a receptor supplies an activation modulation arc to a kinase-activation process; a kinase inhibitor supplies an inhibition T-bar to a separate no-output inhibition process; cargo is transported from cytoplasm to nucleus. Filled consumption/production arrows, hollow stimulation arrows, T-bars, and process glyphs are different.
- `synthetic-failure/input/case.json`: deliberately adds an output to an inhibition process and makes transport start and end in cytoplasm. Both rules must fail before exports and the command must return nonzero.

The work order, original SVG, caption, and tiny data file are software fixtures only. Execute `../scripts/process_semantics.py demo --destination <outside-this-bundle>`.
