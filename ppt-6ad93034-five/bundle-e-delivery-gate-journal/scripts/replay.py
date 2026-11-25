#!/usr/bin/env python3
"""replay.py — build the delivery package and re-verify it.

  replay.py           write /app/output/delivery_manifest.json + RUN_REPORT.md
  replay.py --check   re-verify the journal hash chain AND every manifest
                      artifact hash; exit 1 on tamper or missing file.

Manifest artifact keys are paths RELATIVE to CASE_OUTPUT_DIR so the whole
delivery directory can be copied elsewhere and re-checked in place.
"""
import datetime
import hashlib
import json
import os
import sys

INPUT_DIR = os.environ.get("CASE_INPUT_DIR", "/input")
WORK_DIR = os.environ.get("CASE_WORK_DIR", "/app/work")
OUTPUT_DIR = os.environ.get("CASE_OUTPUT_DIR", "/app/output")
JOURNAL_PATH = os.path.join(WORK_DIR, "journal.jsonl")
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "delivery_manifest.json")
REPORT_PATH = os.path.join(OUTPUT_DIR, "RUN_REPORT.md")
GATE_STAGES = ("plan", "build", "render")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(entry):
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def read_journal():
    entries = []
    if os.path.isfile(JOURNAL_PATH):
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    return entries


def chain_valid(entries):
    if not entries:
        return False
    prev = None
    for e in entries:
        if entry_hash(e) != e.get("hash") or e.get("prev_hash") != prev:
            return False
        prev = e.get("hash")
    return True


def collect_artifacts():
    """sha256 + size of every payload file under OUTPUT_DIR.

    Excludes delivery_manifest.json (cannot hash itself) and RUN_REPORT.md
    (regenerated on every replay run — both are regenerable metadata, not
    payload)."""
    skip = {os.path.abspath(MANIFEST_PATH), os.path.abspath(REPORT_PATH)}
    artifacts = {}
    if not os.path.isdir(OUTPUT_DIR):
        return artifacts
    for root, _dirs, files in os.walk(OUTPUT_DIR):
        for name in sorted(files):
            full = os.path.join(root, name)
            if os.path.abspath(full) in skip:
                continue
            rel = os.path.relpath(full, OUTPUT_DIR)
            artifacts[rel] = {"sha256": sha256_file(full), "bytes": os.path.getsize(full)}
    return artifacts


def read_gates():
    gates = {}
    for stage in GATE_STAGES:
        gp = os.path.join(WORK_DIR, f"gate-{stage}.json")
        if os.path.isfile(gp):
            try:
                with open(gp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                gates[stage] = {"verdict": data.get("verdict"), "ts": data.get("ts")}
            except Exception:
                gates[stage] = {"verdict": "unreadable", "ts": None}
        else:
            gates[stage] = {"verdict": "missing", "ts": None}
    return gates


def honest_notes(entries, gates):
    notes = []
    init = entries[0] if entries else {}
    tools = init.get("tools") or {}
    if tools.get("soffice") is None:
        notes.append("soffice was NOT available during this run: PDF export and preview PNGs "
                     "were skipped and the render gate recorded `renderer-absent` (ok:true). "
                     "The deck is delivered as editable .pptx only.")
    for stage, g in gates.items():
        if g.get("verdict") not in ("PASS",):
            notes.append(f"gate {stage} verdict is {g.get('verdict')} — the run is NOT fully gated.")
    missing = [e["seq"] for e in entries
               for group in ("inputs", "outputs")
               for v in (e.get(group) or {}).values() if v is None]
    if missing:
        notes.append(f"journal entries {missing} recorded files that were already missing (null hashes).")
    if not notes:
        notes.append("no anomalies recorded; renderer present, all gates PASS, all logged files hashed.")
    return notes


def cmd_build():
    entries = read_journal()
    gates = read_gates()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    manifest = {
        "artifacts": collect_artifacts(),
        "journal_hash_chain_valid": chain_valid(entries),
        "journal_entries": len(entries),
        "gates": gates,
        "generated_utc": utc_now(),
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    init = entries[0] if entries else {}
    tools = init.get("tools") or {}
    lines = [
        "# RUN REPORT",
        "",
        f"- generated_utc: {manifest['generated_utc']}",
        f"- journal entries: {len(entries)} (hash chain valid: {manifest['journal_hash_chain_valid']})",
        f"- artifacts in manifest: {len(manifest['artifacts'])} (delivery_manifest.json and "
        f"RUN_REPORT.md are regenerable metadata and intentionally not hashed inside the manifest)",
        "",
        "## Tool versions (recorded at journal init)",
        "",
    ]
    for name, ver in tools.items():
        lines.append(f"- {name}: {ver if ver else 'NOT AVAILABLE'}")
    lines += ["", "## Journal timeline", "", "| seq | kind | note | hash prefix |", "|---:|---|---|---|"]
    for e in entries:
        note = e.get("note") or e.get("cmd") or ("init: inputs+tools hashed" if e.get("kind") == "init" else "")
        note = str(note).replace("|", "\\|")
        lines.append(f"| {e.get('seq')} | {e.get('kind')} | {note} | `{str(e.get('hash'))[:12]}` |")
    lines += ["", "## Gate verdicts", "", "| stage | verdict | ts |", "|---|---|---|"]
    for stage, g in gates.items():
        lines.append(f"| {stage} | {g.get('verdict')} | {g.get('ts')} |")
    lines += ["", "## Artifacts (sha256, bytes)", ""]
    for rel, meta in manifest["artifacts"].items():
        lines.append(f"- `{rel}` — {meta['bytes']} bytes — sha256 `{meta['sha256'][:16]}...`")
    lines += ["", "## Honest notes", ""]
    for n in honest_notes(entries, gates):
        lines.append(f"- {n}")
    lines.append("")
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"replay: wrote {MANIFEST_PATH}")
    print(f"replay: wrote {REPORT_PATH}")
    return 0


def cmd_check():
    ok = True
    entries = read_journal()
    if chain_valid(entries):
        print(f"replay --check: journal hash chain OK ({len(entries)} entries)")
    else:
        print("replay --check: TAMPERED journal — hash chain broken", file=sys.stderr)
        ok = False
    if not os.path.isfile(MANIFEST_PATH):
        print(f"replay --check: manifest missing: {MANIFEST_PATH}", file=sys.stderr)
        return 1
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    for rel, meta in manifest.get("artifacts", {}).items():
        full = os.path.join(OUTPUT_DIR, rel)
        if not os.path.isfile(full):
            print(f"replay --check: MISSING artifact {rel}", file=sys.stderr)
            ok = False
        elif sha256_file(full) != meta.get("sha256"):
            print(f"replay --check: TAMPERED artifact {rel} — recorded sha256 {meta.get('sha256')[:16]}... "
                  f"does not match current bytes", file=sys.stderr)
            ok = False
        else:
            print(f"replay --check: ok {rel}")
    if not ok:
        print("replay --check: FAILED", file=sys.stderr)
        return 1
    print("replay --check: ALL OK")
    return 0


def main():
    if "--check" in sys.argv[1:]:
        return cmd_check()
    return cmd_build()


if __name__ == "__main__":
    sys.exit(main())
