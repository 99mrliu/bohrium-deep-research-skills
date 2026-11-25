#!/usr/bin/env python3
"""verify.py — mechanical evidence integrity audit.

Walks every JSON artifact in --work (and optionally --output) and checks every
object that carries evidence fields:

  * address exists: (source_id, paragraph_id) must exist in corpus.json;
  * quote integrity: "quote" (and "context") must be an EXACT substring of the
    cited paragraph's text (case-sensitive, whitespace-sensitive);
  * no page numbers: artifacts must not invent PDF page numbers.

Writes <work>/verify_report.json and exits non-zero if any check fails.

Usage: python3 verify.py --work /app/work [--output /app/output]
"""
import argparse
import glob
import os
import sys

import kgcommon as K

ARTIFACT_GLOBS = ("*.json",)
SKIP_FILES = {"corpus.json", "run_meta.json"}


def _walk(obj, path=""):
    if isinstance(obj, dict):
        yield obj, path
        for key in sorted(obj):
            yield from _walk(obj[key], "%s.%s" % (path, key))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            yield from _walk(item, "%s[%d]" % (path, idx))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)

    corpus = K.load_json(os.path.join(args.work, "corpus.json"))
    paragraphs = {}
    for src in corpus["sources"]:
        for para in src["paragraphs"]:
            paragraphs[(src["source_id"], para["paragraph_id"])] = para["text"]
    known_pids = {pid for (_, pid) in paragraphs}

    files = []
    for pattern in ARTIFACT_GLOBS:
        files += glob.glob(os.path.join(args.work, pattern))
        if args.output:
            files += glob.glob(os.path.join(args.output, pattern))
    files = sorted({f for f in files
                    if os.path.basename(f) not in SKIP_FILES
                    and os.path.basename(f) != "verify_report.json"})

    checked, passed = 0, 0
    failures = []
    per_file = {}
    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            data = K.load_json(fpath)
        except Exception as exc:
            failures.append({"file": fname, "path": "$", "error": "UNPARSABLE",
                             "detail": str(exc)})
            continue
        f_checked = 0
        for obj, path in _walk(data):
            quote = obj.get("quote", obj.get("context"))
            pid = obj.get("paragraph_id")
            if quote is None or pid is None:
                continue
            f_checked += 1
            sid = obj.get("source_id")
            text = None
            if sid is not None and (sid, pid) in paragraphs:
                text = paragraphs[(sid, pid)]
            elif pid in known_pids:
                text = next(t for (s, p), t in paragraphs.items() if p == pid)
            if text is None:
                failures.append({"file": fname, "path": path,
                                 "error": "ADDRESS_NOT_FOUND",
                                 "detail": "no paragraph %s (source %s)"
                                           % (pid, sid)})
                continue
            if quote not in text:
                failures.append({"file": fname, "path": path,
                                 "error": "QUOTE_NOT_SUBSTRING",
                                 "detail": "quote %r not in paragraph %s"
                                           % (quote[:80], pid)})
                continue
        per_file[fname] = f_checked
        checked += f_checked

    # no invented page numbers anywhere
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as fh:
            content = fh.read()
        for needle in ('"page"', '"page_number"', '"pages"'):
            if needle in content:
                failures.append({"file": os.path.basename(fpath), "path": "$",
                                 "error": "PAGE_NUMBER_PRESENT",
                                 "detail": "this package has no PDF page numbers"})

    passed = checked - sum(1 for f in failures
                           if f["error"] in ("ADDRESS_NOT_FOUND",
                                             "QUOTE_NOT_SUBSTRING"))
    report = {
        "notice": K.NOTICE,
        "files_checked": sorted(per_file),
        "evidence_items_per_file": per_file,
        "evidence_checked": checked,
        "evidence_passed": max(passed, 0),
        "other_failures": sum(1 for f in failures
                              if f["error"] not in ("ADDRESS_NOT_FOUND",
                                                    "QUOTE_NOT_SUBSTRING")),
        "failure_count": len(failures),
        "failures": sorted(failures, key=lambda f: (f["file"], f["path"],
                                                    f["error"])),
        "verdict": "pass" if not failures else "fail",
    }
    out = os.path.join(args.work, "verify_report.json")
    K.dump_json(report, out)
    print("verify: %d/%d evidence item(s) OK across %d file(s); verdict=%s -> %s"
          % (report["evidence_passed"], checked, len(per_file),
             report["verdict"], out))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
