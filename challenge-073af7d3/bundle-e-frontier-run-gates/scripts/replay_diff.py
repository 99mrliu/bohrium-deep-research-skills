#!/usr/bin/env python3
"""replay_diff.py — determinism proof for the scripted stages.

Re-runs mini_pipeline into a shadow directory (<work>/replay/) using the corpus
and case paths recorded in the manifest, then byte-compares (sha256) every
stage artifact against the originals. Any difference means a scripted stage
leaked non-determinism (dict/set iteration, wall-clock, ordering) and the run
must NOT ship until investigated (SKILL.md, section 6).

Usage:
  replay_diff.py --work DIR

Prints a JSON report. Exit 0 when every artifact is byte-identical, 1 on any
difference or setup failure. Stdlib only. No network.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_manifest as rm  # noqa: E402
import mini_pipeline  # noqa: E402

ARTIFACTS = list(mini_pipeline.ARTIFACTS)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic replay diff.")
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    work = os.path.abspath(args.work)

    manifest = rm.load(work)
    if manifest is None:
        print(json.dumps({"status": "error",
                          "error": "manifest_missing: run mini_pipeline first"},
                         ensure_ascii=False))
        return 1
    pipe = manifest.get("pipeline") or {}
    corpus, case = pipe.get("corpus"), pipe.get("case")
    if not corpus or not case:
        print(json.dumps({"status": "error",
                          "error": "pipeline_paths_missing in manifest"},
                         ensure_ascii=False))
        return 1
    if not os.path.isfile(corpus) or not os.path.isfile(case):
        print(json.dumps({"status": "error",
                          "error": "recorded corpus/case file no longer exists"},
                         ensure_ascii=False))
        return 1

    replay_dir = os.path.join(work, "replay")
    if os.path.isdir(replay_dir):
        shutil.rmtree(replay_dir)
    os.makedirs(replay_dir)

    # fresh manifest in the shadow dir, same registered inputs
    shadow = rm.new_manifest()
    for entry in manifest.get("inputs", []):
        if os.path.isfile(entry["path"]):
            rm.add_input(shadow, entry["path"])
    rm.save(replay_dir, shadow)

    try:
        mini_pipeline.run(replay_dir, corpus, case)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error",
                          "error": "replay_failed: %s: %s"
                                   % (type(exc).__name__, exc)},
                         ensure_ascii=False))
        return 1

    files = []
    all_identical = True
    for name in ARTIFACTS:
        orig = os.path.join(work, name)
        repl = os.path.join(replay_dir, name)
        entry = {"file": name}
        if not os.path.isfile(orig):
            entry["identical"] = False
            entry["detail"] = "original_missing"
            all_identical = False
        elif not os.path.isfile(repl):
            entry["identical"] = False
            entry["detail"] = "replay_missing"
            all_identical = False
        else:
            o_sha, r_sha = sha256_file(orig), sha256_file(repl)
            entry["original_sha256"] = o_sha
            entry["replay_sha256"] = r_sha
            entry["identical"] = o_sha == r_sha
            if o_sha != r_sha:
                all_identical = False
        files.append(entry)

    report = {
        "status": "identical" if all_identical else "differ",
        "work": work,
        "replay_dir": replay_dir,
        "files": files,
        "note": "byte-identical artifacts prove the scripted stages are "
                "deterministic and the run is reproducible",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if all_identical else 1


if __name__ == "__main__":
    sys.exit(main())
