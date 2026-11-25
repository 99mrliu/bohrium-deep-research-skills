# Explicit RDF real test report

Scope: 20 SYNTHETIC claims only, not formal research results.

Command run from the Skill root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish.py --case examples/rdf-request/input/case.json --task examples/rdf-request/input/task.md --resources environment/resources.yaml --work examples/rdf-request/work --output examples/rdf-request/actual
```

Observed result: exit 0, elapsed 0.011272 seconds, 0 network requests.

Actual textual deliverables:

- `actual/result.json`: original `SYNTHETIC-RDF-020` and exactly `case_id`, `claims`, `evidence`, `sources`, `uncertainty`, `change_records`, `publications`.
- `actual/nanopubs.trig`: four named graphs with absolute IRIs, all 20 claims reified.
- `actual/nanopubs.jsonld`: the same four expanded named graphs and literals.
- `actual/validation-report.json`: readback, references, graph counts and explicit limitations.
- `work/result.partial.json`, `work/result.candidate.json`, `work/nanopubs.candidate.trig`, and `work/nanopubs.candidate.jsonld`: early partial plus pre-output result/RDF candidates.

Candidate and final readback checks both passed. There are 20 claims, 20 evidence records and 4 sources with complete references. `named_graph_count=4`, `reified_claim_count=20`, and `qualified_direct_triple_leaks=0`. Quad counts: Head 4, assertion 155, provenance 93, pubinfo 3. Head has the three specified part links; provenance references assertion and pubinfo references publication.

Pubinfo has only the publication reference and `local-unregistered` / `not-generated` statuses: the synthetic input supplied no creator, license or creation timestamp, so none was guessed.

Limit: TriG and JSON-LD passed strict generated-subset parsing, quad comparison and nanopub structural checks. This is not a complete W3C conformance validation, external RDF-library parse, registration, or Trusty URI operation. Local IRIs remain local.
