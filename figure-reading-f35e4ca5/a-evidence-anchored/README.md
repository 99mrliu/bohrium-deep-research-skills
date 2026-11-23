# evidence-anchored-figure-reading

Skill for challenge **阅读02｜科研图表解析** (challenge-f35e4ca5).
Center: **upstream data authenticity** — the case's original tables,
caption and text are the source of truth; figure pixels are a hypothesis
verified against them. Every reported number carries a provenance record
(source_type + locator + verbatim + crosscheck status).

- `SKILL.md` — the protocol (runtime contract, workflow, failure catalogue)
- `scripts/mine_case.py` — inventory: table profiles, text blocks, number index, skeleton result.json (stdlib)
- `scripts/anchor_figure.py` — axis-card gates: type-vs-geometry, unit prefix, table-column anchoring (stdlib)
- `scripts/crosscheck.py` — bidirectional figure↔table match matrix (stdlib)
- `scripts/make_result.py` — provenance-gated contract assembly (stdlib)
- `references/` — provenance schema, source-priority and conflict rules
- `examples/` — runnable synthetic miniature (marked as example)

Run the example: `python examples/make_synthetic_case.py`
