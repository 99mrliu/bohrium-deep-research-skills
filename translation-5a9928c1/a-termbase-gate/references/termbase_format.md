# Termbase artifact formats

Three JSON artifacts form the termbase lifecycle. All are UTF-8, deterministic
(stable ordering), and safe to diff in version control.

## Lifecycle

```
 source text (.txt/.md/.pdf)
        │  extract_terms.py
        ▼
 termbase_draft.json ──(agent writes translations.json)──► lock_termbase.py
        │                                                     │
        │                                                     ▼
        │                                            termbase.locked.json
        │                                                     │  audit_translation.py
        │                                                     ▼
        └──────────────── coverage sections echoed into ── audit_report.json
```

**draft → locked → audited**. Once locked, `target` values MUST NOT change;
re-locking (even with the same inputs) regenerates `termbase_sha256`, so any
tampering is detectable.

## 1. termbase_draft.json (extract_terms.py output)

| field | type | meaning |
|---|---|---|
| `source_files` | array | `[{path, sha256}]` — provenance of every input file |
| `entries` | array | candidate terms, sorted by frequency desc then term |
| `stats` | object | `{files, entries, acronyms, phrases}` counts |

Each entry:

| field | type | meaning |
|---|---|---|
| `id` | string | `T001`, `T002`, … stable within one draft |
| `source_term` | string | English term exactly as it appears (whitespace-normalized) |
| `acronym` | string\|null | e.g. `"PSC"` for acronym-kind entries |
| `kind` | string | `"acronym"` (from `Full Name (ACR)` pattern) or `"phrase"` (repeated n-gram) |
| `frequency` | int | occurrences in the source text (full name + acronym for acronym kind) |
| `sections` | array | section names where the term was seen |
| `target` | null | **always null in a draft** — filled at lock time |
| `forbidden_variants` | array | **always empty in a draft** |

## 2. translations.json (agent-authored input to lock_termbase.py)

Top-level object mapping `source_term` → either a bare string or an object:

```json
{
  "perovskite solar cell": {
    "target": "钙钛矿太阳能电池",
    "forbidden_variants": ["钙钛矿电池", "钙钛矿太阳电池"]
  },
  "charge transport layer": "电荷传输层",
  "_drop": [
    {"source_term": "Methylammonium Lead", "reason": "sub-phrase of kept longer entry"}
  ]
}
```

| key | meaning |
|---|---|
| `<source_term>`: string | shorthand for `{"target": string, "forbidden_variants": []}` |
| `<source_term>.target` | the **single mandated** Chinese rendering; non-empty |
| `<source_term>.forbidden_variants` | renderings that must never appear for this term |
| `_drop` | list of `{"source_term", "reason"}` (or bare strings) for candidates to discard |

Rules enforced by `lock_termbase.py`:
- every non-dropped draft entry must get a non-empty `target` (else exit 1, unless `--allow-partial`);
- `forbidden_variants` must not contain the `target` itself (hard error);
- duplicate targets across entries → warning only (legitimate for synonyms).

## 3. termbase.locked.json (lock_termbase.py output)

| field | type | meaning |
|---|---|---|
| `locked` | bool | always `true` |
| `status` | string | `"locked"` or `"partial"` (with `--allow-partial` + uncovered entries) |
| `source_files` | array | carried over from the draft |
| `entries` | array | draft entries with `target`/`forbidden_variants` filled; dropped ones carry `"dropped": true` |
| `dropped` | array | `[{source_term, reason}]` |
| `uncovered` | array | source_terms still lacking a target (empty on full lock) |
| `warnings` | array | non-fatal issues (e.g. duplicate targets) |
| `termbase_sha256` | string | sha256 of the canonical JSON of `entries` (sorted keys, compact separators) — integrity anchor |

`audit_translation.py` echoes `termbase_sha256` into every audit report, tying a
report to exactly one locked termbase.

## Maintaining a termbase across documents

1. **Reuse, don't rebuild.** For a new paper in the same domain, run
   `extract_terms.py` on the new text, then merge its *new* candidates into the
   existing `translations.json` (old targets keep precedence).
2. **Never edit `termbase.locked.json` by hand.** Change `translations.json`,
   re-run `lock_termbase.py`, expect a new sha256, re-audit all documents that
   cite the old sha.
3. **Grow forbidden_variants from real violations.** Every `term-drift` hit in an
   audit is a candidate new forbidden variant.
4. **Keep `_drop` reasons honest.** "not a domain term", "sub-phrase of T007",
   "out of scope (units)" — future maintainers depend on them.
5. **One termbase per project/domain**, not per paragraph; fragmentation defeats
   consistency governance.
