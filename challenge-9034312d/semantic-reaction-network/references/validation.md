# Semantic validation and negative controls

## Error gates

`srn.py` returns 1 and withholds the final SVG on any semantic error. Reports remain available for repair. Checks cover:

1. unique node/edge/port/compartment/source IDs and schema version;
2. declared compartments and node-kind compatibility for all endpoints;
3. existing output/input ports with compatible carrier types;
4. mandatory source references on required nodes and every interaction;
5. enzyme/catalyst-only catalysis sources and cross-compartment transport;
6. explicit non-generic activation/inhibition markers;
7. directed cycles, feedback membership, and acyclicity after feedback removal;
8. weak connectivity of all required nodes, including readouts/charts;
9. exact branch/join edge sets, modes, evidence, and XOR conditions;
10. sourced acyclic phase dependencies;
11. actual readable CSV, unique headers, mapped x/y/series columns, numeric finite rows;
12. original-source semantic mismatches.

Unknown source references and unsupported required mechanisms are errors. Missing declared source files are warnings leading to partial status; they do not become fiction. I/O/parse failures return 2.

## Negative test

`scripts/test_negative.py` loads the positive synthetic graph and creates temporary mutants that it submits to two complete builds:

- it retypes the actual inhibition edge as `material_flow` with a generic arrow; signal/material port incompatibility and source mismatch must reject it;
- it redirects catalysis from readout to chart; endpoint type incompatibility must reject it.

The negative harness succeeds only if the original has no errors, both builds return nonzero, and the expected codes are detected. Temporary failed results are removed when the test context closes. A validator that merely draws all JSON would fail this test. For an additional manual nonzero check, copy the input graph into a work directory, apply the same inhibition mutation, and invoke `srn.py`; inspect exit code 1 and `validation_report.json`.

## Rendered audit

After XML parsing/export, inspect the PNG and machine-readable SVG:

- inhibitory paths terminate in a bar, activation paths in the special open/+ mark;
- paths connect the intended nodes and ports, without arrow reversal due to layout;
- required entities and readouts are connected and visible within compartments;
- feedback labels occur only on explicit cyclic edges;
- fan-in/fan-out matches all/any/xor semantics and conditions;
- sequence phase order is visible and not represented as material flow;
- each chart series matches the supplied CSV rows and headers; no third series or smoothing appears;
- SVG retains stable layer IDs and semantic `data-*` attributes.

A maximum of two correction/review rounds after extraction prevents endless cosmetic cycles. Reserve the last inspection for semantics changed by the first correction.
