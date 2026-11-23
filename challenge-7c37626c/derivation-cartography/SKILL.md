---
name: derivation-cartography
description: Map the derivation structure of a paper — formula dependency graph from citation and symbol-flow edges, assumption/approximation radar over the prose, and a fail-closed completeness gate for derivation step skeletons; use whenever a task asks to explain how results follow from each other, to decompose a derivation into checkable steps, or to state the assumptions under which each step holds.
---

# derivation-cartography: reasoning-structure mapping (推得顺 · 推导审计)

Core stance: **a derivation is a graph, and a step without a justification is
a missing fact.** This skill's center of gravity is the reasoning structure:
which formula feeds which result, what assumption licenses each transition,
and which steps the paper states explicitly versus which the reader must
reconstruct. It does not transcribe formulas and does not recompute numbers —
it maps how results depend on each other and gates on whether every claimed
step is checkable.

## Runtime contract

- Input: `/input/case.json` and `task.md`; materials under
  `case.json.artifacts` (publisher XML with formula nodes and prose, a
  formula subset XML, possibly a PDF). Read the actual files.
- Create `/app/work` immediately; write `/app/output/result.json` early as an
  honest partial containing the original `case_id` and every
  `output_contract` field; improve it incrementally.
- Final `result.json` uses the contract's own field names, types and status
  enumeration. Missing-formula branch (no formula representation at all):
  derivation mapping is impossible — report `insufficient_evidence` and name
  the missing objects; never reverse-engineer a derivation from metrics.
- Do not submit prepared answers: every node, edge and step in the output
  comes from the actual run on the actual input.

## Workflow

1. **Bootstrap.** `python3 scripts/case_bootstrap.py --input /input --work /app/work --out /app/output`
   writes the early partial `result.json`.
2. **Build the graph.** `python3 scripts/graph_build.py --case /input/case.json --input /input --work /app/work`.
   Nodes: every math node with its id, display label (from `<label>`) and
   section context. Edges, each with verbatim evidence: (a) **citation
   edges** — prose like "Equation (1)", "Eq. (2)", 式(1), "substituting … into
   …" linking a text location to a labeled formula; (b) **symbol-flow
   edges** — a symbol used in formula A that was first introduced in formula
   B's context. Citations whose label matches no formula are recorded as
   `unresolved_citations` — identify by original IDs and labels, never by
   guessing from position. Output: `graph.json` (nodes, edges, evidence),
   `graph.mmd` (Mermaid for reuse), and `graph.png` when matplotlib is
   available (fallback: Mermaid only, recorded as a note).
3. **Run the assumption radar.** `python3 scripts/assumption_radar.py --case /input/case.json --input /input --work /app/work`
   scans the prose for assumption/approximation/boundary markers (assume,
   approximation, valid for, under the condition, neglect, limit, first
   order, 假设, 近似, 边界, …), anchors each hit to its section and nearby
   formulas, and writes `assumptions.json`. Hits are evidence-bearing quotes,
   not paraphrases.
4. **Write the step skeleton and gate it.** The agent decomposes the key
   derivation into steps following `references/step_skeleton.template.md` and
   writes `/app/work/steps.json`. Then
   `python3 scripts/step_gate.py --work /app/work --out /app/output`
   enforces completeness: every step carries `from`, `to`, `action`,
   `justification` (the algebraic rule or citation, not a vibe), `locator`,
   and an `assumptions` list (possibly empty, but present). Steps referencing
   formulas absent from the graph, or steps without justification, fail the
   gate: the affected chain is reported and the case status degrades to
   `partial` with the defective steps named.
5. **Finalize.** `result.json` carries the graph summary (node/edge counts,
   unresolved citations), the assumption inventory, the gated step skeleton,
   and links to `graph.mmd`/`graph.png` and the reports.

## Exception handling

- No labeled formulas: citation edges are skipped with a note; symbol-flow
  edges still build the graph; the limitation is recorded.
- Conflicting labels (two nodes with the same label): both are listed, the
  citation is `unresolved`, never arbitrated silently.
- Steps the agent cannot justify: omit the step and name the gap in
  `uncertainty` — a missing step is better than an invented one.
- Corrupt XML: downstream of whatever parser output exists; status degrades
  and the parse error is quoted.

## Minimal example (SYNTHETIC — not a platform case, not evidence)

`examples/run_synthetic_example.sh` maps a fabricated two-formula paper
(Einstein relation feeding a consistency check), detects the assumption
"when the electric field vanishes", demonstrates an honestly unresolved
citation label, and gates a two-step skeleton — one complete, one defective
so the gate's fail-closed behavior is visible. All materials are synthetic.

## Requirements and limitations

Python 3.9+ standard library; matplotlib optional for `graph.png` (the
Mermaid source is always produced). Citation and assumption detection is
pattern-based: it finds candidate edges and quotes them as evidence, and the
agent must confirm semantics. The gate checks the *presence* of
justifications, not their mathematical truth — that belongs to the reading
agent and to numerical verification skills.
