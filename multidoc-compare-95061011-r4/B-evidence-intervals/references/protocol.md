# Evidence-first reading protocol

## 1. Establish comparability before numbers

Read the task, workorder, captions, methods, and metric definitions before collecting results. For every requested cell, write down:

- comparison and task identity;
- metric name and operational definition;
- requested unit and whether a conversion is justified;
- exact material and dataset/experiment identity;
- exact pollutant/dye identity (never merge different dyes);
- budget or condition, such as initial concentration, dose, time, temperature, or denominator;
- whether evidence is direct, derived, inferred, or absent.

A matching number with a different denominator or pollutant belongs to a different claim. A conversion cannot repair a changed experimental budget.

## 2. Locate intervals in reading order

1. Find the metric definition, table title, header, or equation. Use it as a `definition` interval when it is needed to interpret the result.
2. Capture the smallest result-bearing `support` interval. Offsets are Unicode code-point offsets into the indexed paragraph, with `end` exclusive.
3. Add only the `context` interval(s) needed to establish material, pollutant, metric, unit, and budget. Context can precede or follow the result and can be in a separate paragraph.
4. Bind each qualifier to the span IDs that literally establish it. The validator checks containment independently; declaring that context exists is insufficient.
5. Retain exact text in `quote`. Normalization for matching uses Unicode NFC, casefolding for qualifier tests, common Unicode hyphen folding, and whitespace collapse. Original source text and byte hashes remain unchanged so version drift is visible.

Do not select a whole paper as a context interval. If several disjoint paragraphs are truly needed, use several intervals and explain the uncertainty. Do not discard a qualifier merely because it occurs in a header rather than the result sentence.

## 3. Direct, derived, inferred, absent

**Direct.** The result literal and unit must be present in support evidence. Context must establish all qualifiers.

**Derived.** Provide named numeric operands, their units and evidence-span references, a restricted arithmetic formula, a result unit, and a justification. The implementation evaluates only numeric AST nodes and `+`, `-`, `*`, `/`, unary signs, and parentheses. Unit conversion factors must be explicit operands or documented constants in the formula. A derived value is not a direct quote and must not be presented as one.

**Inference.** Keep agent reasoning separate from source evidence. It may help form a hypothesis, but remains excluded from factual quantitative synthesis. If a numeric inference is retained, it is visibly labelled and never promoted to direct evidence.

**Absent.** Search the entire indexed source using the metric synonyms and relevant table/method terms. Use `value_type: absent`, `value: not_reported`, `paragraph_id: null`, an empty `source_spans` list, and a `search_scope` listing every indexed paragraph ID and the queries used. A searched scope is necessary; a fabricated source paragraph or placeholder quote is forbidden.

## 4. Independent context-completeness tests

Validation fails when any of these is false:

- document and paragraph IDs exist and the span's document matches the record;
- offsets are in range, quote equals the indexed slice under normalized comparison, and hashes match;
- exactly one support interval exists for direct/derived/inference records;
- quantitative direct/derived records have context and valid qualifier-to-span bindings;
- each material, pollutant, metric, unit, and budget string occurs in its declared spans;
- the direct result literal occurs in support and the requested task/metric/unit match the workorder;
- derived operands refer to actual spans, their literals occur there, and the formula reproduces the value;
- absence search covers the complete document and has real queries.

The smallest sufficient interval remains a reader decision, but these checks make omission and unsupported claims mechanically visible.

## 5. Conflicts and noncomparability

If one paper gives unequal values for the same comparison, field, material, pollutant, metric, unit, and budget, retain every record with the same non-empty `conflict_group` and `status: conflicted`. Explain the disagreement in `uncertainty`. A singleton conflict group is invalid. If values differ and no conflict group is supplied, validation fails rather than choosing silently.

Distinct experimental conditions can coexist without being a conflict when their qualifier keys differ. They remain separate rows. The renderer performs no pooling and labels cross-condition aggregation `noncomparable`; this is a valid completed comparison, not automatically a partial run.

## 6. Final synthesis

Render only records that passed validation. Keep invalid records in the ledger as excluded with errors. Missing document/comparison evidence produces a `missing_evidence_record` row and partial status, not a false `not_reported` conclusion. Invalid evidence with some valid rows yields partial; no usable matrix or fatal indexing failure yields failed. A complete validated run with absent or noncomparable cells can be successful.
