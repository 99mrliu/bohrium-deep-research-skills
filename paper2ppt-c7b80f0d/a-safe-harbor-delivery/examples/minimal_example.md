# Minimal End-to-End Example (ILLUSTRATION ONLY — not an official case result)

This shows one complete invocation sequence against a *mock* case. Paths assume the harness
defaults; everything is overridable by flags.

## Mock setup

```bash
mkdir -p /tmp/demo/input /tmp/demo/work /tmp/demo/output
cat > /tmp/demo/input/case.json <<'EOF'
{
  "case_id": "demo-001",
  "constraints": {"slide_limit": 8, "language": "en", "duration_minutes": 10},
  "output_contract": {"required_fields": ["slide_deck_path", "slide_count", "key_findings"]}
}
EOF
echo "Make an 8-slide academic deck from the attached paper." > /tmp/demo/input/task.md
pdftotext -layout /tmp/demo/input/paper.pdf /tmp/demo/work/paper.txt   # mock paper omitted here
```

## P0 — scaffold (first ~90 s)

```bash
S=/skills/weekly-skill/scripts
python3 $S/scaffold_output.py --case /tmp/demo/input/case.json --task /tmp/demo/input/task.md \
    --outdir /tmp/demo/output --workdir /tmp/demo/work
# scaffold OK
#   case_id        : demo-001
#   contract fields: ['slide_deck_path', 'slide_count', 'key_findings']
#   slide limit    : 8
#   slide plan     : ['title','problem','gap','method','evidence-1','limitations','conclusions','backup']

python3 $S/build_skeleton_deck.py --state /tmp/demo/work/session_state.json \
    --out /tmp/demo/output/deck.pptx --titles-from /tmp/demo/work/paper.txt
# skeleton deck built: /tmp/demo/output/deck.pptx   (backend: stdlib-minipptx)

python3 $S/validate_output.py --outdir /tmp/demo/output --case /tmp/demo/input/case.json \
    --state /tmp/demo/work/session_state.json
# deliverable_state: partial      <-- valid submission already exists
```

示意 `result.json` after P0:

```json
{
  "case_id": "demo-001",
  "status": "partial",
  "slide_deck_path": {"status": "pending", "detail": "not yet produced; P0 scaffold placeholder"},
  "slide_count":   {"status": "pending", "detail": "not yet produced; P0 scaffold placeholder"},
  "key_findings":  {"status": "pending", "detail": "not yet produced; P0 scaffold placeholder"},
  "sources": [],
  "uncertainty": ["Paper content not yet extracted (P0 scaffold).", "..."]
}
```

## P2 — upgrade one slide (repeat in priority order)

```bash
printf -- '- Deep nets underperform on streaming tabular data (§1).\n- Existing methods assume i.i.d. batches (§1).\n' \
  > /tmp/demo/work/extract/02-problem.bullets.txt
printf '30s: motivate streaming setting; transition: so what is missing?\n' \
  > /tmp/demo/work/extract/02-problem.notes.txt

python3 $S/patch_slide.py --deck /tmp/demo/output/deck.pptx --slide 2 \
    --title "Problem & Background" \
    --bullets-file /tmp/demo/work/extract/02-problem.bullets.txt \
    --notes-file  /tmp/demo/work/extract/02-problem.notes.txt \
    --footer "Source: §1 Introduction"
# patched slide 2/8 OK (1 done, 7 pending)
```

## P3 — render & verify

```bash
python3 $S/render_preview.py --deck /tmp/demo/output/deck.pptx --outdir /tmp/demo/output/preview
# render status: ok -> /tmp/demo/output/render_manifest.json   (or renderer_unavailable: disclose!)
python3 $S/validate_output.py --outdir /tmp/demo/output --case /tmp/demo/input/case.json \
    --state /tmp/demo/work/session_state.json
```

示意 `render_manifest.json` (renderer present):

```json
{"status": "ok", "slide_count": 8, "png_count": 8,
 "tools": {"soffice": "/usr/bin/soffice", "soffice_version": "LibreOffice 24.8",
           "pdftoppm": "/usr/bin/pdftoppm"}}
```

## P4 — finalize result.json

```json
{
  "case_id": "demo-001",
  "status": "partial",
  "slide_deck_path": "/tmp/demo/output/deck.pptx",
  "slide_count": 8,
  "key_findings": ["...verbatim finding 1 (Table 1)...", "...verbatim finding 2 (Fig. 3)..."],
  "sources": ["/tmp/demo/input/paper.pdf"],
  "uncertainty": ["Slide 6 evidence slide kept as placeholder: time checkpoint fired at 80%."],
  "change_record": [
    {"ts": "...", "phase": "P0", "action": "scaffold", "detail": "valid partial set created"},
    {"ts": "...", "phase": "P2", "action": "patch_slide", "detail": "slides 1-5,7-8 filled"},
    {"ts": "...", "phase": "P3", "action": "render", "detail": "8 PNG previews verified"}
  ]
}
```

Final `validate_output.py` prints `deliverable_state: partial` (one placeholder left,
honestly disclosed) — or `complete` if all slides were filled and render verified.

*Reminder: all paths, counts and JSON above are illustrative, produced against a mock case —
not an official challenge result.*
