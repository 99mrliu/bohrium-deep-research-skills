# Canonical MathML IR specification (version 1)

## 1. Purpose and unit of evidence

The extraction unit is each XML element whose local tag is `math`. Each occurrence is retained independently in document order for each lexically sorted source path. The catalog records:

- `formula_key`: deterministic, filename-safe occurrence key; collisions receive a deterministic source suffix instead of overwriting another formula;
- `source.path`: path relative to the selected input root when possible;
- `source.id`: `math/@id`, otherwise the nearest formula/ancestor id, otherwise an empty string;
- `source.label`: `math/@label` or direct `label` text of the owning formula;
- `source.section`: nearest section's direct title, or its id if no title exists;
- `ordered_path`: root-to-node steps containing `tag`, one-based `child_index` among element siblings, and one-based `tag_index` among same-tag element siblings;
- `xpath`: a same-tag-index rendering of that ordered path;
- canonical IR, generated LaTeX, detailed roundtrip results, render issues, and independent publisher-string checks.

An IR file is the notation evidence for one `math` node, not a claim about the node’s scientific meaning.

## 2. Canonical JSON node

Every element is exactly one JSON object with four fields:

```json
{
  "tag": "mfrac",
  "attributes": {"linethickness": "1px"},
  "text": "",
  "children": [
    {"tag": "mi", "attributes": {}, "text": "x", "children": []},
    {"tag": "mn", "attributes": {}, "text": "2", "children": []}
  ]
}
```

Rules:

1. `tag` is the XML local name. Namespace-qualified input tags such as `{http://www.w3.org/1998/Math/MathML}mrow` become `mrow`.
2. `attributes` retains every parsed attribute name and string value. Expanded attribute names such as `{namespace}name` retain that ElementTree spelling. Canonical JSON uses lexically sorted attribute keys. No attribute is used merely as metadata and then discarded.
3. `text` is the element’s parsed `text` string verbatim (`""` if absent). This includes formatting text directly inside a container.
4. `children` contains every child element recursively and in original order. There is no grouping, flattening, reassociation, sorting, or operator precedence rewrite.
5. Token text in `mi`, `mn`, `mo`, and `mtext` therefore retains source Unicode and all operator characters. Attributes such as `form`, `fence`, `separator`, `stretchy`, scripts, scriptsizemultiplier, mathvariant, and display remain available even when the basic LaTeX renderer does not style them.
6. Canonical serialization uses UTF-8 JSON, sorted object keys, no ASCII escaping requirement, and no Unicode normalization. In particular, NFC/NFD/NFKC/NFKD are not applied. Canonically distinct source characters are never deliberately NFKC-merged. Explicit TeX codepoint mappings used for display do not mutate the IR.

### Explicit XML boundaries

The canonical IR is MathML-element-structure equivalence, not byte-level or complete XML Infoset equivalence. It omits element namespace URI/prefix once reduced to a local tag, comments, processing instructions, and child `tail` strings. Tail strings between child elements are treated as inter-element layout. This prevents pretty-print indentation after a child from becoming a second semantic representation. Mixed-content constructs with meaningful tails are outside the guaranteed subset. Element `text` itself is retained and roundtripped. Standard XML entity expansion performed by the stdlib parser happens before IR construction; no external resource loader is provided.

## 3. Supported subset and unsupported behavior

The guaranteed structural/rendering subset is:

```text
math mrow mfrac msub msup msubsup msqrt mroot mfenced
munder mover munderover mtable mtr mlabeledtr mtd mi mn mo mtext
mstyle mpadded mphantom mspace menclose semantics annotation annotation-xml
```

Unknown elements are still recursively captured and serialized by the lossless generic tree serializer. They are **not** accepted as supported semantics:

- the renderer emits `\text{[UNSUPPORTED MathML:TAG]}`;
- `render_issues` contains `unsupported_tag` with the precise IR path;
- `unsupported_nodes` lists every occurrence, not just the first;
- roundtrip status is `unsupported` even if canonical structure compares equal;
- extraction reports overall `partial`, and strict verification exits `2`.

Malformed fixed-arity supported nodes similarly get an explicit `INVALID MathML` LaTeX marker and an `invalid_arity` issue. No unknown node is dropped and replaced by an empty string.

## 4. LaTeX notation rules

The renderer uses recursive structure rather than linear token concatenation:

- every `mfrac`, script, root, under/over, and cell operand is braced where TeX parsing requires operand boundaries;
- `msubsup` produces `{base}_{subscript}^{superscript}` with both pieces retained;
- `mroot` preserves MathML child order as `\sqrt[index]{base}`;
- multi-character `mi` becomes one `\mathit{...}` token; it is never split into separate letters;
- `mfenced/@open`, `close`, and `separators` become explicit `\left`/`\right` fences and inserted separators;
- `mtable`/`mtr`/`mtd` becomes `matrix`, rows, and cells;
- operators use explicit source-codepoint mappings or escaped literal characters, without normalizing the source IR;
- `mtext` becomes `\text{...}` with TeX special-character escaping;
- `munderover` nests `\underset` and `\overset`, preserving all three operands;
- `mstyle`/`mpadded` are transparent notation wrappers, `mphantom` maps to `\phantom`, and `mspace` becomes an explicit fixed space;
- `semantics` renders only its non-annotation body while preserving annotations in IR; annotation nodes themselves produce no visible operand;
- radical or boxed `menclose` uses the corresponding root/box notation; other enclosure notations retain a visible review marker and a render issue;
- `mlabeledtr` is treated as a table row in basic LaTeX, while its label/style attributes remain available in IR.

These rules prioritize an inspectable notation mapping, not optimal typographic style. For example, spacing introduced between adjacent children is renderer syntax, not invented MathML operator evidence. Core LaTeX cannot encode every MathML display attribute; IR remains the lossless evidence of those attributes.

## 5. Canonical roundtrip and discrepancy meaning

For every formula the verifier performs:

```text
canonical IR A
  -> recursive ElementTree serialization
  -> UTF-8/unicode MathML string
  -> stdlib XML parse
  -> canonical IR B
  -> exhaustive compare(A, B)
```

Comparison covers, at every path:

- tag and element text;
- missing, unexpected, and differently valued attributes;
- child count;
- every paired child recursively;
- every extra/missing child beyond the paired length;
- roundtrip parse errors.

Each discrepancy has a path and kind (`value_mismatch`, `attribute_mismatch`, `missing_attribute`, `unexpected_attribute`, `child_count_mismatch`, `missing_child`, `unexpected_child`, or `roundtrip_parse_error`). It does not stop after the first mismatch.

Statuses:

- `pass`: no discrepancy and no unsupported node;
- `mismatch`: at least one canonical discrepancy or parse failure;
- `unsupported`: canonical structures match but at least one unsupported tag exists.

`canonical_equal` and `supported_subset` are separate fields by design. Roundtrip verification proves serializer/parser preservation within section 2’s stated IR boundaries only. It does **not** establish notation semantics, scientific validity, derivation validity, or numerical correctness.

## 6. Independent publisher strings

`math/@alttext` and an associated direct `tex-math` sibling in the immediate/alternatives container receive separate comparison objects. Each contains its own status, original publisher text, `authoritative: false`, and an explanatory note.

Statuses are `absent`, `exact_match`, `whitespace_match`, and `mismatch`. Whitespace comparison only collapses whitespace for the comparison result; neither generated nor publisher text is modified. No publisher string is converted into IR, copied into generated LaTeX as truth, used to repair a discrepancy, or allowed to turn `unsupported` into `pass`.

Consequently, `exact_match` means only “generated notation happens to equal this independent string.” `mismatch` is a review signal, not automatic proof that either representation is scientifically wrong. A contradictory publisher string cannot hide the explicit unsupported-tag result.

## 7. Relationship to result analysis

The catalog and IR do not auto-answer scientific fields. `assemble_result.py` merges actual agent-authored formula, variable, derivation, and numeric analysis with factual extraction metadata under the runtime’s dynamic contract. Missing authored fields remain empty/explicit or become a reported `null` type issue; they are never replaced with plausible values. Zero `math` nodes yields `insufficient_evidence` and an empty formula claim set. This boundary prevents mechanical extraction from masquerading as domain analysis.
