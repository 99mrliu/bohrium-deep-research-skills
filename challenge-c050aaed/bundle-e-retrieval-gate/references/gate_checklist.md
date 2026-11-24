# Gate Checklist

`scripts/gate.py` is the pre-delivery audit. It writes
`gate_report.json {checks:[{name,pass,detail}], verdict, failed}`, exits 0 when
every check passes, and exits 3 otherwise — rewriting `result.json` to
`status: "partial"` and appending the failed check names to its
`uncertainty`/`limitations` field (all other fields preserved). An unfinished
result can never masquerade as complete. Exit 2 means the gate itself was
invoked wrongly (missing `--case`/`--index`/`--smoke-queries`/`--output-dir`,
or an unparsable case/index file).

## 1. contract_completeness

**What:** `result.json` exists in the output dir, parses as JSON, its
`case_id` equals the case's, and every field named by the case's
`output_contract` is a top-level key of `result.json`. The contract is read
dynamically from `--case` — a list is used as-is, a dict contributes its
`fields` list (or its keys). If the case has no `output_contract`, that fact is
recorded in the detail and only `case_id` is checked.

**Why:** the evaluator scores exactly the fields the case names; a missing
field is a silent zero, and a wrong `case_id` misattributes the whole result.

**Fix when failing:** add the named fields to `result.json` (re-reading
`case.json` — never guess names), or correct `case_id`. If `result.json` was
missing entirely, the gate cannot rewrite it: recreate it with
`status: "partial"` immediately and improve in place.

## 2. artifact_integrity

**What:** every entry of `result.json`'s `artifacts` map
(`{name: {path, sha256}}`) exists under the output dir and its file's actual
sha256 equals the recorded one. If `result.json` references no artifacts, the
check passes vacuously and says so.

**Why:** `result.json` is a claim about files; this check makes the claim
verifiable and catches truncated writes, stale paths, and post-hoc edits.

**Fix when failing:** regenerate or restore the named artifact, then refresh
its recorded `sha256` in `result.json`. If an artifact was renamed, update the
path — do not delete the entry to make the check pass.

## 3. verification_rates

**What:** every `*.json` file in the output dir whose name contains `verify`
or `claims` must meet thresholds: `anchors.verified / anchors.total` ≥
`--min-anchor-rate` (default 0.95) **and** `anchors.failed == 0`; note claims
`notes_claims.verified == notes_claims.total` (rate exactly 1.0). Finding **no**
such report is a failure, as is a report with an unrecognized schema.

**Why:** precipitated knowledge is only as good as its evidence. Unverified
anchors or unbacked claims must block delivery, not ride along silently.

**Fix when failing:** return to the verification step and re-verify the failed
anchors/claims against the source files, or honestly downgrade: remove claims
whose evidence cannot be confirmed rather than relaxing thresholds. Only lower
`--min-anchor-rate` if the task itself sanctions a different bar.

## 4. retrieval_smoke

**What:** each entry of `smoke.json` (`{q, must_find_id}` plus optional
`tag/type/file/since/until` filters) is run against the index; `must_find_id`
must appear in the **top 5** hits. An entry with `must_find_id: null` is a
negative control and must return zero hits.

**Why:** an index that cannot find items we *know* are in it would fail every
downstream 后续检索 request; this is the cheapest known-item recall test.

**Fix when failing:** re-run the failing query by hand with `query.py` and read
the no-hit/low-confidence report. Usual causes: the item was never indexed
(check build doc counts), the smoke query's terms do not literally occur in the
document (fix the smoke query — matching is literal, not semantic), or an
over-strict filter in the smoke entry. A failing negative control means the
index matches text it should not contain — check for stale inputs.

## 5. replay_determinism

**What:** the gate reads the input paths recorded in the index `meta.inputs`,
locates them relative to the cwd, the index's directory, or its parent, re-runs
`build_index.build(...)` with the recorded path strings, and byte-compares the
rebuilt index with the shipped `index.json`.

**Why:** proves the shipped index is exactly what the deterministic builder
produces from the stated inputs — not stale after an upstream re-run, not
hand-edited, not tampered. Together with the query log, this makes every
reported retrieval result replayable by a reviewer.

**Fix when failing:** rebuild the index from the current inputs with
`build_index.py` and reship it (then re-run the smoke test). If the input
files moved, the detail says the originals were not found: restore them or
rebuild from their new location so `meta.inputs` is truthful. Never patch
`index.json` by hand.

## After any failure

1. Read `gate_report.json` → the `failed` list and per-check `detail`.
2. Fix the cause above; keep `result.json` honest (skips, conflicts,
   recoveries go into `uncertainty`/`change_records`).
3. Re-run the gate. Deliver only on exit 0 / `verdict: "pass"`.
