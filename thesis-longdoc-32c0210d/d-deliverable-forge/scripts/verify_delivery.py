#!/usr/bin/env python3
"""verify_delivery.py — final delivery check; writes manifest.json.

Checks:
  C1 result-parseable   result.json parses as JSON
  C2 case-id            result case_id equals case.json case_id
  C3 contract-keys      every output_contract.fields key exists in result.json;
                        a null value is only acceptable if "problems" has an
                        entry for that field (honest partial, not silent null)
  C4 artifacts-hashed   every declared artifact exists under the output dir and
                        is hashed (sha256) into manifest.json; any artifact
                        under preview/ must additionally be non-empty (a real
                        rendered file, never a fabricated placeholder)
  C5 chapters-consistent every chapter named in result.edited_chapters exists in
                        the output dir and is byte-identical to the latest
                        working copy in <work-dir>/chapters/

result.json itself is always hashed into the manifest.
Exit codes: 0 = all checks pass; 1 = at least one check failed (manifest still
written); 2 = result.json/case.json unreadable.
"""
import argparse
import hashlib
import json
import os
import sys

PREVIEW_DIR = "preview/"


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Final delivery verification; emits manifest.json.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--result", required=True, help="path to result.json")
    ap.add_argument("--output-dir", required=True, help="real output dir (stands in for /app/output)")
    ap.add_argument("--work-dir", required=True, help="work dir holding chapters/ working copies")
    ap.add_argument("--manifest", required=True, help="path to write manifest.json")
    ap.add_argument("--note", default=None, help="optional note copied into manifest.json")
    args = ap.parse_args()

    checks = []

    def check(cid, ok, detail):
        checks.append({"id": cid, "ok": bool(ok), "detail": detail})
        print("%s %-22s %s" % ("PASS" if ok else "FAIL", cid, detail))
        return ok

    try:
        with open(args.result, encoding="utf-8") as f:
            result = json.load(f)
        check("C1-result-parseable", True, "result.json parses as JSON")
    except (OSError, json.JSONDecodeError) as e:
        print("FAIL C1: result.json unreadable: %s" % e, file=sys.stderr)
        return 2

    try:
        with open(args.case, encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("FAIL: case.json unreadable: %s" % e, file=sys.stderr)
        return 2

    # ---- C2: case_id ----------------------------------------------------------
    check("C2-case-id", result.get("case_id") == case.get("case_id"),
          "result case_id %r vs case.json %r" % (result.get("case_id"), case.get("case_id")))

    # ---- C3: contract keys present; null requires a problem record ------------
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    fields = contract.get("fields") if isinstance(contract.get("fields"), list) else []
    problems = result.get("problems") if isinstance(result.get("problems"), list) else []
    problem_fields = {p.get("field") for p in problems if isinstance(p, dict)}
    for field in fields:
        if field not in result:
            check("C3-contract-keys", False, "contract key %r missing from result.json" % field)
        elif result[field] is None:
            check("C3-contract-keys", field in problem_fields,
                  "key %r is null%s" % (field, " with matching problem record (honest partial)"
                                        if field in problem_fields else " WITHOUT problem record"))
        else:
            check("C3-contract-keys", True, "key %r filled" % field)

    # ---- C4: artifacts exist + hashed; preview files must be non-empty --------
    manifest_entries = []
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        check("C4-artifacts-hashed", False, "result.artifacts is not a list")
        artifacts = []
    for rel in artifacts:
        if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
            check("C4-artifacts-hashed", False, "bad artifact path %r" % (rel,))
            continue
        full = os.path.join(args.output_dir, rel)
        if not os.path.isfile(full):
            check("C4-artifacts-hashed", False, "declared artifact missing: %s" % rel)
            continue
        size = os.path.getsize(full)
        if rel.startswith(PREVIEW_DIR) and size == 0:
            check("C4-artifacts-hashed", False, "preview artifact is EMPTY (would be a fake): %s" % rel)
            continue
        manifest_entries.append({"path": rel, "sha256": sha256_of(full), "bytes": size})
        check("C4-artifacts-hashed", True, "%s sha256=%s (%d bytes)"
              % (rel, sha256_of(full)[:12] + "…", size))

    # result.json itself always goes into the manifest
    if os.path.isfile(args.result):
        manifest_entries.append({"path": "result.json", "sha256": sha256_of(args.result),
                                 "bytes": os.path.getsize(args.result)})

    # ---- C5: edited chapters identical to latest work copies ------------------
    edited = result.get("edited_chapters")
    if edited is None:
        check("C5-chapters-consistent", True,
              "edited_chapters is null (see problems); skipped")
    elif not isinstance(edited, dict):
        check("C5-chapters-consistent", False,
              "edited_chapters must be an object mapping chapter -> output-relative path")
    else:
        for name in sorted(edited):
            rel = edited[name]
            out_path = os.path.join(args.output_dir, rel) if isinstance(rel, str) else None
            work_path = os.path.join(args.work_dir, "chapters", name)
            if not isinstance(rel, str) or not out_path or not os.path.isfile(out_path):
                check("C5-chapters-consistent", False, "output copy missing for chapter %r" % name)
            elif not os.path.isfile(work_path):
                check("C5-chapters-consistent", False,
                      "no working copy %s to compare against" % work_path)
            elif sha256_of(out_path) != sha256_of(work_path):
                check("C5-chapters-consistent", False,
                      "chapter %r: output copy differs from latest work copy" % name)
            else:
                check("C5-chapters-consistent", True,
                      "chapter %r identical to work copy" % name)

    ok = all(c["ok"] for c in checks)
    manifest = {
        "case_id": result.get("case_id"),
        "generated_by": "verify_delivery.py",
        "ok": ok,
        "checks": checks,
        "artifacts": manifest_entries,
    }
    if args.note:
        manifest["note"] = args.note
    os.makedirs(os.path.dirname(os.path.abspath(args.manifest)), exist_ok=True)
    atomic_write_json(args.manifest, manifest)

    print("verify: %s; manifest -> %s" % ("ALL CHECKS PASS" if ok else "CHECKS FAILED", args.manifest))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
