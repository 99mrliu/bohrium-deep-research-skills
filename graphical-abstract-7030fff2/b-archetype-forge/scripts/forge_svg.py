#!/usr/bin/env python3
"""forge_svg.py -- Bundle B (ga-archetype-forge): instantiate an archetype.

Usage:
  python3 forge_svg.py --archetype hub-mechanism --params /app/work/params.json \
      --out /app/output/graphical_abstract.svg

The params JSON schema per archetype is documented in
references/archetype_guide.md. This program only assembles geometry; every
label/number in params must already be source-anchored by the agent (see
SKILL.md step 2 — forge_svg.py re-checks that params["sources"] entries are
verbatim substrings of the material pool if --pool is given, and refuses to
forge unanchored content).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archetypes

WS_RE = re.compile(r"\s+")


def norm(s):
    return WS_RE.sub(" ", s or "").strip()


def verify_sources(params, pool_text):
    pool = norm(pool_text)
    problems = []
    for i, src in enumerate(params.get("sources", [])):
        q = norm(src.get("quote", ""))
        if not q:
            problems.append("sources[%d] empty quote" % i)
        elif q not in pool:
            problems.append("sources[%d] quote not verbatim in pool: %r"
                            % (i, q[:70]))
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archetype", required=True,
                    choices=sorted(archetypes.ARCHETYPES))
    ap.add_argument("--params", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pool", default=None,
                    help="source_pool.txt for verbatim anchoring check")
    args = ap.parse_args()

    with open(args.params, encoding="utf-8") as fh:
        params = json.load(fh)

    problems = []
    if args.pool:
        with open(args.pool, encoding="utf-8") as fh:
            problems = verify_sources(params, fh.read())
    if problems:
        print(json.dumps({"forged": False, "anchor_problems": problems},
                         indent=2, ensure_ascii=False))
        return 1

    svg = archetypes.ARCHETYPES[args.archetype](params)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(json.dumps({"forged": True, "archetype": args.archetype,
                      "out": args.out, "bytes": len(svg.encode("utf-8")),
                      "anchored_sources": len(params.get("sources", []))},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
