# Edge taxonomy for the derivation graph

| type | meaning | evidence recorded |
|-|-|-|
| `citation` | prose names a labeled formula ("Equation (2)", 式(2)) | verbatim context window around the mention |
| `substitution` | prose states a substitution of one formula/value into another ("substituting μ0 into Equation (1)") | the substitution sentence, truncated to 200 chars |
| `symbol_flow` | a symbol used in formula A was first introduced in formula B's context | symbol name and introducing node id |

## Resolution discipline

- Citations resolve through the **label map** (`<label>(2)</label>` of a
  `disp-formula`). Never resolve by position ("the first formula is (1)")
  unless the source itself labels it.
- A citation label with no matching formula, or matching several, goes to
  `unresolved_citations` with its context — an honest hole in the map, not a
  guessed edge.
- Symbol-flow edges are structural hypotheses: they say where a symbol
  entered, not that the paper *derived* A from B. The reading agent decides
  which flows are genuine derivation steps and writes them into
  `steps.json`.
- Text nodes (`text:<section>`) are allowed edge endpoints so that prose-only
  dependencies (definitions, parameter choices) still appear in the map.
