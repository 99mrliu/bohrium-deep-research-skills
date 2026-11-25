# Journal and manifest schema (librepair.py)

## manifest.json (survey)

```json
{
  "tool": "librepair.py survey",
  "generated_at": "<utc iso>",
  "root": "<abs path>",
  "file_count": 0,
  "files": [
    {"path": "<rel>", "name": "...", "ext": ".txt", "is_symlink": false,
     "size": 0, "mtime": "<utc iso>", "mode": "-rw-r--r--",
     "readable": true, "sha256": "<64 hex>", "magic": "text-like|pdf|...",
     "norm_stem": "<normalized>", "version_hint": [2, 0]}
  ],
  "duplicates": [{"sha256": "...", "paths": ["a", "a (1)"]}],
  "version_suspects": [{"norm_stem": "notes", "ext": ".txt",
                        "paths": ["notes v1.txt", "notes v2.txt"]}],
  "errors": [{"path": "...", "stage": "survey", "error": "..."}]
}
```

## journal.jsonl (apply) — one JSON object per line

```json
{"seq": 1, "ts": "<utc iso>", "op": "copy", "src": "<rel src>",
 "dst": "<rel dst>", "sha256": "<hash of both, verified equal>",
 "ok": true, "error": null, "chain": "<sha256(prev_chain + entry)>"}
```

`op` ∈ {copy, alias_record, version_chain, skip, finalize}.
`chain` of the first entry uses prev = 64 zeroes. Any edit, deletion, or
reordering of lines breaks the chain and is detected by `verify`.

## verify_report.json

```json
{"dest": "...", "journal_entries": 0, "copies_verified": 0,
 "problems": [{"kind": "journal_chain_break|missing_copy|hash_drift|"
                        "source_not_represented", "..."}],
 "ok": true}
```

`ok: false` must propagate into result.json as a named conflict; a clean
report is the strongest verifiability evidence this skill produces.
