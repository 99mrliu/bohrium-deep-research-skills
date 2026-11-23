# Synthetic example task (NOT an official case)

This file mimics the shape of the platform task file for local self-checks only.
All data in `case.json` and `material-batch-c.csv` are invented; nothing here is an
official case, a whiteboard, or an expected answer.

Goal exercised by this example: clean heterogeneous literature-extraction records —
map differently-named headers onto a versioned canonical schema with explicit
confidence and evidence, infer semantic types, split range columns, normalize units
defensibly, keep missing values null, flag duplicates conservatively without merging
scientific conflicts, and emit the full audit trail (cleaned CSV/JSON, mapping report,
unresolved schema, review queue, change log, audit.md, result.json).
