#!/usr/bin/env python3
"""librepair.py - safe, journaled document-library repair toolkit.

Pure Python 3 standard library (3.8+). No third-party dependencies.

Subcommands:
  survey    Read-only forensic inventory of a materials directory.
  plan      Build a conservative repair plan (duplicates, aliases,
            version chains) from a manifest plus optional admin notes.
  apply     Execute the plan as COPY-ONLY operations into a destination
            tree, journaling every action with before/after hashes.
  verify    Re-hash the destination, check journal hash-chain integrity,
            and confirm no source file was lost.
  rollback  Undo an apply run in reverse journal order, refusing to
            touch any file whose content drifted from the journal.

Design rules:
  * NEVER delete, move, or overwrite an original input file.
  * Every mutation is journaled BEFORE it is considered done; the journal
    is hash-chained so later tampering is detectable.
  * Anything ambiguous is flagged for review, not silently resolved.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import sys

CHUNK = 1 << 20

# Markers stripped when normalising a file stem for alias/version clustering.
COPY_PATTERNS = [
    r"\s*\(\d+\)$",                 # "file (1)"
    r"\s*（\d+）$",
    r"\s*\(v?\d+(?:\.\d+)*\)$",     # "file (v2)"
    r"\s*（v?\d+(?:\.\d+)*）$",
    r"[\s_\-]+v\d+(?:\.\d+)*$",     # "file v2", "file_v2", "file-v2"
    r"[\s_\-]+副本$",
    r"\s*副本$",
    r"[\s_\-]+copy(?:\s*\d*)$",
    r"[\s_\-]+final(?:\s*\d*)$",
    r"[\s_\-]+draft(?:\s*\d*)$",
    r"[\s_\-]+new$",
    r"[\s_\-]+old$",
]

VERSION_RE = re.compile(r"[vV](\d+(?:\.\d+)*)")

MAGICS = [
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "zip-or-office"),
    (b"\x89PNG", "png"),
    (b"\xff\xd8\xff", "jpeg"),
]


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            buf = fh.read(CHUNK)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def sniff_magic(path):
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return "unreadable"
    for sig, name in MAGICS:
        if head.startswith(sig):
            return name
    try:
        head.decode("utf-8")
        return "text-like"
    except UnicodeDecodeError:
        return "binary-other"


def norm_stem(name):
    stem = os.path.splitext(name)[0].strip().lower()
    changed = True
    while changed:
        changed = False
        for pat in COPY_PATTERNS:
            new = re.sub(pat, "", stem, flags=re.IGNORECASE)
            if new != stem:
                stem = new.strip()
                changed = True
    return stem


def version_of(name):
    m = VERSION_RE.search(os.path.splitext(name)[0])
    if not m:
        return None
    parts = m.group(1).split(".")
    return [int(p) for p in parts]


def is_text_name(name):
    return os.path.splitext(name)[1].lower() in (
        ".txt", ".md", ".markdown", ".json", ".jsonl", ".csv", ".tsv",
        ".yaml", ".yml", ".xml", ".html", ".htm", ".bib", ".ris", ".log",
    )


# ---------------------------------------------------------------- survey

def cmd_survey(args):
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("survey: not a directory: %s" % root, file=sys.stderr)
        return 2
    files = []
    errors = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            entry = {"path": rel, "name": fn,
                     "ext": os.path.splitext(fn)[1].lower(),
                     "is_symlink": os.path.islink(full)}
            try:
                st = os.lstat(full)
                entry["size"] = st.st_size
                entry["mtime"] = datetime.datetime.fromtimestamp(
                    st.st_mtime, datetime.timezone.utc).isoformat()
                entry["mode"] = stat.filemode(st.st_mode)
                entry["readable"] = os.access(full, os.R_OK)
                if entry["readable"] and not entry["is_symlink"]:
                    entry["sha256"] = sha256_file(full)
                    entry["magic"] = sniff_magic(full)
                    entry["norm_stem"] = norm_stem(fn)
                    entry["version_hint"] = version_of(fn)
                else:
                    entry["sha256"] = None
                    entry["magic"] = "unreadable"
                    errors.append({"path": rel, "stage": "survey",
                                   "error": "unreadable or symlink"})
            except OSError as exc:
                entry["error"] = str(exc)
                errors.append({"path": rel, "stage": "survey",
                               "error": str(exc)})
            files.append(entry)

    by_hash = {}
    for e in files:
        if e.get("sha256"):
            by_hash.setdefault(e["sha256"], []).append(e["path"])
    duplicates = [{"sha256": h, "paths": sorted(ps)}
                  for h, ps in sorted(by_hash.items()) if len(ps) > 1]

    clusters = {}
    for e in files:
        if e.get("norm_stem") is not None:
            key = (e["norm_stem"], e["ext"])
            clusters.setdefault(key, []).append(e["path"])
    version_suspects = [
        {"norm_stem": k[0], "ext": k[1], "paths": sorted(v)}
        for k, v in sorted(clusters.items()) if len(v) > 1
    ]

    manifest = {
        "tool": "librepair.py survey",
        "generated_at": utcnow(),
        "root": root,
        "file_count": len(files),
        "files": files,
        "duplicates": duplicates,
        "version_suspects": version_suspects,
        "errors": errors,
    }
    write_json(args.out, manifest)
    print("survey: %d files, %d duplicate groups, %d version-suspect "
          "clusters, %d errors -> %s"
          % (len(files), len(duplicates), len(version_suspects),
             len(errors), args.out))
    return 0


# ------------------------------------------------------------------ plan

def parse_admin_notes(paths):
    """Extract explicit administrative statements about versions/duplicates.

    Recognised (Chinese or English) per line:
      * "X 替代 Y" / "X supersedes Y" / "X replaces Y"  -> successor edge
      * "Y 作废" / "Y deprecated" / "Y obsolete"         -> deprecated mark
      * "X 与 Y 重复" / "X duplicate of Y"               -> duplicate edge
    Returns a list of {kind, a, b, evidence_line, source_file}.
    """
    rules = []
    if not paths:
        return rules
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for line in lines:
            text = line.strip()
            if not text:
                continue
            m = re.search(r"[《\"'`]([^《\"'`]+)[》\"'`]\s*(?:替代|取代|supersedes?|replaces?)\s*[《\"'`]?([^《\"'`\s，。；;,]+)", text, re.I)
            if m:
                rules.append({"kind": "supersedes", "a": m.group(1),
                              "b": m.group(2).strip("》\"'`,，。；;"),
                              "evidence_line": text, "source_file": p})
                continue
            m = re.search(r"(\S+?\.?\w*)\s*(?:替代|取代|supersedes?|replaces?)\s*(\S+)", text, re.I)
            if m:
                rules.append({"kind": "supersedes", "a": m.group(1),
                              "b": m.group(2).strip("，。；;,"),
                              "evidence_line": text, "source_file": p})
                continue
            m = re.search(r"(\S+?)\s*(?:已作废|已废弃|作废|废弃|deprecated|obsolete)", text, re.I)
            if m:
                rules.append({"kind": "deprecated", "a": m.group(1), "b": None,
                              "evidence_line": text, "source_file": p})
                continue
            m = re.search(r"(\S+?)\s*(?:与|和|and)\s*(\S+?)\s*(?:重复|内容相同|duplicate)", text, re.I)
            if m:
                rules.append({"kind": "duplicate", "a": m.group(1),
                              "b": m.group(2), "evidence_line": text,
                              "source_file": p})
    return rules


def pick_canonical(paths, manifest_files):
    """Choose the canonical member of a duplicate/alias group.

    Preference: fewest copy markers in the name, then shortest name,
    then earliest mtime. Fully deterministic.
    """
    info = {e["path"]: e for e in manifest_files}

    def marker_count(p):
        name = os.path.basename(p).lower()
        return sum(1 for pat in COPY_PATTERNS
                   if re.search(pat, os.path.splitext(name)[0],
                                flags=re.IGNORECASE))

    def key(p):
        e = info.get(p, {})
        return (marker_count(p), len(os.path.basename(p)),
                e.get("mtime") or "9999", p)

    return sorted(paths, key=key)[0]


def cmd_plan(args):
    manifest = read_json(args.manifest)
    files = manifest.get("files", [])
    by_path = {e["path"]: e for e in files}
    notes_rules = parse_admin_notes(args.notes or [])
    actions = []

    # 1. Duplicate groups (identical sha256).
    for group in manifest.get("duplicates", []):
        paths = group["paths"]
        canonical = pick_canonical(paths, files)
        actions.append({
            "action": "register_duplicate_group",
            "sha256": group["sha256"],
            "canonical": canonical,
            "duplicates": [p for p in paths if p != canonical],
            "basis": "identical sha256; canonical = fewest copy markers, "
                     "shortest name, earliest mtime",
            "needs_review": False,
        })

    # 2. Version clusters (same normalised stem + ext, different content).
    for cluster in manifest.get("version_suspects", []):
        paths = cluster["paths"]
        hashes = {by_path.get(p, {}).get("sha256") for p in paths}
        if len(hashes) <= 1:
            # identical content: already handled as a duplicate group
            continue
        members = []
        for p in paths:
            e = by_path.get(p, {})
            members.append({
                "path": p,
                "version_hint": e.get("version_hint"),
                "mtime": e.get("mtime"),
                "sha256": e.get("sha256"),
            })

        def order_key(m):
            return (m["version_hint"] is None,
                    m["version_hint"] or [0],
                    m["mtime"] or "9999", m["path"])

        ordered = sorted(members, key=order_key)
        chain = [m["path"] for m in ordered]
        explicit = any(r["kind"] == "supersedes" and
                       any(r["a"] in p or r["b"] in p for p in paths)
                       for r in notes_rules)
        actions.append({
            "action": "register_version_chain",
            "norm_stem": cluster["norm_stem"],
            "chain_oldest_to_newest": chain,
            "latest": chain[-1] if chain else None,
            "basis": ("explicit administrative note" if explicit else
                      "heuristic: version markers, then mtime"),
            "needs_review": not explicit and len(chain) > 1,
        })

    # 3. Administrative statements that match no file are reported, not dropped.
    all_paths = [e["path"] for e in files]
    unmatched = []
    for r in notes_rules:
        targets = [r.get("a"), r.get("b")]
        hit = any(t and any(t in p for p in all_paths) for t in targets if t)
        if not hit:
            unmatched.append(r)

    plan = {
        "tool": "librepair.py plan",
        "generated_at": utcnow(),
        "manifest": os.path.abspath(args.manifest),
        "notes_files": [os.path.abspath(p) for p in (args.notes or [])],
        "notes_rules": notes_rules,
        "unmatched_notes_rules": unmatched,
        "actions": actions,
        "policy": {
            "mutation": "copy-only into destination; originals never touched",
            "ambiguous": "flagged needs_review, never silently resolved",
            "conflicts": "recorded in journal and result, never hidden",
        },
    }
    write_json(args.out, plan)
    print("plan: %d actions (%d duplicate groups, %d version chains), "
          "%d admin rules, %d unmatched rules -> %s"
          % (len(actions),
             sum(1 for a in actions
                 if a["action"] == "register_duplicate_group"),
             sum(1 for a in actions
                 if a["action"] == "register_version_chain"),
             len(notes_rules), len(unmatched), args.out))
    return 0


# ----------------------------------------------------------------- apply

def journal_entry(chain, entry):
    payload = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((chain + payload).encode("utf-8")).hexdigest()


def cmd_apply(args):
    plan = read_json(args.plan)
    root = os.path.abspath(args.root)
    dest = os.path.abspath(args.dest)
    if dest == root or dest.startswith(root + os.sep):
        print("apply: destination must NOT be inside the source tree",
              file=sys.stderr)
        return 2
    os.makedirs(dest, exist_ok=True)
    chain = "0" * 64
    journal_rows = []

    def log(op, **kw):
        nonlocal chain
        entry = {"seq": len(journal_rows) + 1, "ts": utcnow(), "op": op}
        entry.update(kw)
        chain = journal_entry(chain, entry)
        entry["chain"] = chain
        journal_rows.append(entry)

    def safe_copy(src_rel, dst_rel):
        src = os.path.join(root, src_rel)
        dst = os.path.join(dest, dst_rel)
        try:
            before = sha256_file(src)
        except OSError as exc:
            log("copy", src=src_rel, dst=dst_rel, ok=False,
                error="source unreadable: %s" % exc)
            return False
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            log("copy", src=src_rel, dst=dst_rel, ok=False,
                error="destination exists; skipped to avoid overwrite")
            return False
        try:
            shutil.copy2(src, dst)
            after = sha256_file(dst)
        except OSError as exc:
            log("copy", src=src_rel, dst=dst_rel, ok=False, error=str(exc))
            return False
        ok = before == after
        log("copy", src=src_rel, dst=dst_rel, sha256=before, ok=ok,
            error=None if ok else "hash mismatch after copy")
        return ok

    copied = set()
    for act in plan.get("actions", []):
        if act["action"] == "register_duplicate_group":
            canon = act["canonical"]
            if safe_copy(canon, os.path.join("canonical", canon)):
                copied.add(canon)
            for dup in act.get("duplicates", []):
                # Duplicates are NOT re-copied; the relationship is recorded
                # in ALIASES.json. Originals stay untouched.
                log("alias_record", canonical=canon, alias=dup,
                    basis=act.get("basis"), ok=True)
        elif act["action"] == "register_version_chain":
            chain_paths = act["chain_oldest_to_newest"]
            latest = act.get("latest")
            for p in chain_paths:
                if p == latest and p not in copied:
                    if safe_copy(p, os.path.join("canonical", p)):
                        copied.add(p)
                else:
                    if safe_copy(p, os.path.join("versions",
                                                 act["norm_stem"], p)):
                        copied.add(p)
            log("version_chain", norm_stem=act["norm_stem"],
                path_chain=chain_paths, latest=latest,
                basis=act.get("basis"),
                needs_review=act.get("needs_review", False), ok=True)

    # Files not covered by any action are still copied so the organised
    # library is complete; they keep their relative paths.
    manifest = read_json(plan["manifest"])
    covered = set()
    for act in plan.get("actions", []):
        covered.update(act.get("paths", []))
        covered.update(act.get("chain_oldest_to_newest", []))
        if act.get("canonical"):
            covered.add(act["canonical"])
        covered.update(act.get("duplicates", []))
    for e in manifest.get("files", []):
        p = e["path"]
        if p in covered or not e.get("sha256"):
            if p in covered and p not in copied and e.get("sha256"):
                # covered only as alias of a duplicate group: skip re-copy
                continue
            if not e.get("sha256"):
                log("skip", src=p, reason=e.get("magic", "unreadable"),
                    ok=True)
            continue
        if safe_copy(p, os.path.join("canonical", p)):
            copied.add(p)

    aliases = [a for a in plan.get("actions", [])
               if a["action"] == "register_duplicate_group"]
    versions = [a for a in plan.get("actions", [])
                if a["action"] == "register_version_chain"]
    write_json(os.path.join(dest, "ALIASES.json"),
               {"generated_at": utcnow(), "duplicate_groups": aliases})
    write_json(os.path.join(dest, "VERSIONS.json"),
               {"generated_at": utcnow(), "version_chains": versions,
                "notes_rules": plan.get("notes_rules", []),
                "unmatched_notes_rules":
                    plan.get("unmatched_notes_rules", [])})
    log("finalize", artifacts=["ALIASES.json", "VERSIONS.json"], ok=True)

    write_jsonl(args.journal, journal_rows)
    n_fail = sum(1 for r in journal_rows if not r.get("ok"))
    print("apply: %d journal entries, %d failures, dest=%s"
          % (len(journal_rows), n_fail, dest))
    return 0 if n_fail == 0 else 1


# ---------------------------------------------------------------- verify

def cmd_verify(args):
    dest = os.path.abspath(args.dest)
    rows = read_jsonl(args.journal)
    problems = []

    chain = "0" * 64
    for row in rows:
        expect = journal_entry(chain, {k: v for k, v in row.items()
                                       if k != "chain"})
        if row.get("chain") != expect:
            problems.append({"kind": "journal_chain_break",
                             "seq": row.get("seq")})
        chain = row.get("chain", expect)

    copied_srcs, copied_dsts = {}, {}
    for row in rows:
        if row.get("op") == "copy" and row.get("ok"):
            copied_srcs[row["src"]] = row.get("sha256")
            copied_dsts[row["dst"]] = row.get("sha256")

    for dst_rel, want in copied_dsts.items():
        full = os.path.join(dest, dst_rel)
        if not os.path.exists(full):
            problems.append({"kind": "missing_copy", "dst": dst_rel})
            continue
        got = sha256_file(full)
        if got != want:
            problems.append({"kind": "hash_drift", "dst": dst_rel,
                             "journal": want, "actual": got})

    lost = []
    if args.manifest:
        manifest = read_json(args.manifest)
        for e in manifest.get("files", []):
            h = e.get("sha256")
            if not h:
                continue
            if h in copied_srcs.values():
                continue
            # covered by an alias relationship?
            aliased = any(
                r.get("op") == "alias_record" and r.get("alias") == e["path"]
                for r in rows)
            if not aliased:
                lost.append(e["path"])
    for p in lost:
        problems.append({"kind": "source_not_represented", "path": p})

    report = {
        "tool": "librepair.py verify",
        "generated_at": utcnow(),
        "dest": dest,
        "journal_entries": len(rows),
        "copies_verified": len(copied_dsts),
        "problems": problems,
        "ok": not problems,
    }
    write_json(args.out, report)
    print("verify: %d copies checked, %d problems -> %s"
          % (len(copied_dsts), len(problems), args.out))
    return 0 if not problems else 1


# -------------------------------------------------------------- rollback

def cmd_rollback(args):
    dest = os.path.abspath(args.dest)
    rows = read_jsonl(args.journal)
    removed, kept = [], []
    for row in reversed(rows):
        if row.get("op") != "copy" or not row.get("ok"):
            continue
        full = os.path.join(dest, row["dst"])
        if not os.path.exists(full):
            kept.append({"dst": row["dst"], "reason": "already absent"})
            continue
        got = sha256_file(full)
        if got != row.get("sha256"):
            kept.append({"dst": row["dst"],
                         "reason": "content drifted; NOT removed",
                         "journal": row.get("sha256"), "actual": got})
            continue
        os.remove(full)
        removed.append(row["dst"])
    # prune now-empty directories, deepest first
    for dirpath, dirnames, filenames in os.walk(dest, topdown=False):
        if dirpath != dest and not os.listdir(dirpath):
            os.rmdir(dirpath)
    print("rollback: removed %d copies, kept %d (drift or absent)"
          % (len(removed), len(kept)))
    for k in kept:
        print("  kept: %s (%s)" % (k["dst"], k["reason"]))
    return 0 if not any("drifted" in k["reason"] for k in kept) else 1


# ------------------------------------------------------------------ util

def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("survey", help="read-only forensic inventory")
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_survey)

    p = sub.add_parser("plan", help="build conservative repair plan")
    p.add_argument("--manifest", required=True)
    p.add_argument("--notes", nargs="*", default=[])
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("apply", help="copy-only journaled execution")
    p.add_argument("--plan", required=True)
    p.add_argument("--root", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--journal", required=True)
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("verify", help="re-hash and audit")
    p.add_argument("--dest", required=True)
    p.add_argument("--journal", required=True)
    p.add_argument("--manifest", default=None)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("rollback", help="undo an apply run")
    p.add_argument("--dest", required=True)
    p.add_argument("--journal", required=True)
    p.set_defaults(func=cmd_rollback)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
