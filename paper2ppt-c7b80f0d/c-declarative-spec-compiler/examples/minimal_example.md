# Minimal end-to-end example (EXAMPLE — not a formal case result)

This walkthrough uses a toy 2-slide-plus-overflow spec to show the full
interface: validate → compile (builtin backend) → compile_report → preview.
All content is invented for illustration and marked as such.

## 1. The spec (`deck.spec.json`)

```json
{
  "meta": {
    "case_id": "example-demo",
    "title": "Caching Improves Retrieval Latency (EXAMPLE)",
    "audience": "group meeting",
    "language": "en",
    "slide_limit": 2,
    "max_bullets": 3,
    "footer_prefix": "Source: "
  },
  "slides": [
    {"id": "s1", "kind": "title",
     "title": "Caching Improves Retrieval Latency",
     "claim": "A two-level cache cut p99 latency from 412 ms to 96 ms.",
     "notes": "Open with the demo trace; 20 seconds."},
    {"id": "s2", "kind": "content",
     "claim": "The L2 cache absorbs 78% of misses at 4.1x lower p99 latency.",
     "bullets": ["Setup: 10M queries, Zipf alpha 1.2",
                 "p99: 412 ms baseline -> 96 ms cached",
                 "Misses absorbed by L2: 78%",
                 "Cost: +3.2 GB RAM per node",
                 "Rollout: 5% canary for 2 weeks"],
     "evidence": [{"ref": "Table 2", "page": 7,
                   "quote": "p99 latency drops from 412 ms to 96 ms"}],
     "notes": "Emphasize the canary plan; expect the RAM-cost question."},
    {"id": "s3", "kind": "figure",
     "claim": "Latency improvement holds across all load levels.",
     "image": {"path": "fig_latency.png", "caption": "Fig. 3 (EXAMPLE): p99 vs load"},
     "evidence": [{"ref": "Fig. 3", "page": 8}],
     "notes": "Point at the high-load tail."}
  ]
}
```

Deliberate violations to show the compiler at work: 5 bullets with
`max_bullets: 3` (two demoted to notes) and 3 slides with `slide_limit: 2`
(one moved to the backup section).

## 2. Validate

```bash
python3 scripts/validate_spec.py --spec deck.spec.json
```

Output (exit 0 — these are compiler-managed warnings, not errors):

```
WARN  [slides[1] id='s2'] 5 bullets > meta.max_bullets=3; compiler will demote surplus bullets into speaker notes
WARN  [slides] 3 non-backup slides > meta.slide_limit=2; compiler will move overflow slides into a labelled backup section

validate_spec.py: OK (2 warning(s)); 3 slide(s) in /app/work/deck.spec.json
```

## 3. Compile (no template → builtin backend)

```bash
python3 scripts/compile_deck.py --spec deck.spec.json \
  --out /app/output/deck.pptx --report /app/output/compile_report.json
```

Output:

```
compile_deck: OK backend=builtin slides=4 -> /app/output/deck.pptx
  deviations: no organizer template; builtin plain 16:9 theme used (not the organizer's master, fonts, or footers)
```

## 4. compile_report.json (excerpt)

```json
{
  "compiler": "compile_deck.py 1.0.0",
  "backend": "builtin",
  "backend_reason": "no organizer template/starting deck provided",
  "deviations": ["no organizer template; builtin plain 16:9 theme used ..."],
  "slide_count": {"spec": 3, "emitted": 4, "slide_limit": 2, "backup_overflow": 1},
  "decisions": [
    {"slide": "s2", "kind": "content", "actions": [
      "bullet-cap: 2 bullet(s) over meta.max_bullets=3 demoted to notes [DEMOTED:bullet-cap]"]},
    {"slide": "_backup_divider", "kind": "backup", "actions": []}
  ],
  "warnings": ["slide-limit: 1 slide(s) over meta.slide_limit=2 moved to backup section"]
}
```

Notes on slide s2 now contain the original notes plus
`[DEMOTED:bullet-cap] Cost: +3.2 GB RAM per node` and
`[DEMOTED:bullet-cap] Rollout: 5% canary for 2 weeks`; slide s3 appears after
a "Backup / Appendix" divider; the evidence footer on s2 reads
"Source: Table 2 (p. 7)".

## 5. Render + inspect

```bash
python3 scripts/render_preview.py --deck /app/output/deck.pptx \
  --outdir /app/output/preview --manifest /app/output/render_manifest.json
```

Then open `/app/output/preview/slide-*.png` and verify: title/banner/bullets
fit, footer stamped, figure not distorted, backup slides labelled. If soffice
is unavailable the manifest reports `"status": "renderer_unavailable"` and the
script still exits 0 — disclose that in `result.json` uncertainty.

## 6. result.json

```bash
python3 scripts/make_result.py --case /input/case.json \
  --out /app/output/result.json --status complete \
  --uncertainty "builtin backend (no organizer template); preview renderer_unavailable on this machine"
```
