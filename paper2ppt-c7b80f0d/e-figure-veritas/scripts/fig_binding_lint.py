#!/usr/bin/env python3
"""fig_binding_lint.py — 引用绑定门禁：deck 结构源里的每个图引用必须合法。

deck.json 最小模式：
{
  "deck_title": "...",
  "slides": [
    {"n": 1, "role": "title|background|methods|results|discussion|limitations|
                      conclusion|...",
     "title": "...", "claims": ["..."],
     "figures": [{"id": "fig1",
                  "provenance": "original-crop|redrawn-from-data|schematic-reference",
                  "path": "figs/redrawn_fig1.png"}],
     "table": null | "table1",
     "sources": [{"kind": "paper|data|template", "ref": "paper.pdf",
                  "locator": "p.4 Table 1", "quote": "<逐字原文>"}],
     "notes": "...", "notes_time_sec": 60}
  ]
}

检查项（error 级）：
  E1 unknown-figure        引用的 figure id 不在 manifest
  E2 bad-provenance        provenance 缺失或不在合法三值内
  E3 schematic-in-results  results 角色页挂了 manifest 判定为 schematic 的图
  E4 unknown-kind          引用了 kind=unknown 且未经裁决的图
  E5 unknown-table         引用的 table id 不在 manifest
警告级：
  W1 provenance-mismatch   original-crop 但 manifest 无抽取文件；
                           redrawn-from-data 但 path 不含 redrawn 标记
  W2 missing-file          path 指向的文件不存在
任一 error → 退出码 1；仅警告/全部通过 → 0；输入错误 → 2。
"""
import argparse
import json
import os
import sys

PROVENANCES = ("original-crop", "redrawn-from-data", "schematic-reference")
RESULTS_ROLES = ("results",)


def main():
    ap = argparse.ArgumentParser(
        description="Lint figure bindings in deck.json against figure_manifest.json.")
    ap.add_argument("deck", help="deck.json (structure source of the deck)")
    ap.add_argument("manifest", help="figure_manifest.json (post fig_classify.py)")
    ap.add_argument("--report", default="binding_report.json")
    args = ap.parse_args()

    try:
        with open(args.deck, encoding="utf-8") as fh:
            deck = json.load(fh)
        with open(args.manifest, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read inputs: {exc}\n")
        return 2

    fig_index = {f["id"]: f for f in manifest.get("figures", [])}
    tab_index = {t["id"]: t for t in manifest.get("tables", [])}
    deck_dir = os.path.dirname(os.path.abspath(args.deck))

    errors, warnings = [], []

    def err(slide, code, msg):
        errors.append({"slide": slide, "code": code, "message": msg})

    def warn(slide, code, msg):
        warnings.append({"slide": slide, "code": code, "message": msg})

    for slide in deck.get("slides", []):
        n = slide.get("n")
        role = slide.get("role", "unknown")
        for ref in slide.get("figures", []):
            fid = ref.get("id")
            prov = ref.get("provenance")
            if fid not in fig_index:
                err(n, "unknown-figure",
                    f"figure id '{fid}' not in manifest")
                continue
            fmeta = fig_index[fid]
            if prov not in PROVENANCES:
                err(n, "bad-provenance",
                    f"figure '{fid}' provenance '{prov}' not in {list(PROVENANCES)}")
            kind = fmeta.get("kind", fmeta.get("kind_hint", "unknown"))
            if role in RESULTS_ROLES and kind == "schematic":
                err(n, "schematic-in-results",
                    f"results slide {n} binds schematic figure '{fid}' "
                    f"(caption: {fmeta.get('caption', '')[:80]})")
            if kind == "unknown":
                err(n, "unknown-kind",
                    f"figure '{fid}' kind is unknown; adjudicate before use")
            if prov == "original-crop" and not fmeta.get("file"):
                warn(n, "provenance-mismatch",
                     f"'{fid}' tagged original-crop but manifest has no extracted file")
            if prov == "redrawn-from-data" and "redrawn" not in (ref.get("path") or ""):
                warn(n, "provenance-mismatch",
                     f"'{fid}' tagged redrawn-from-data but path lacks 'redrawn': "
                     f"{ref.get('path')}")
            path = ref.get("path")
            if path:
                full = path if os.path.isabs(path) else os.path.join(deck_dir, path)
                if not os.path.isfile(full):
                    warn(n, "missing-file", f"figure file not found: {path}")
        tab = slide.get("table")
        if tab and tab not in tab_index:
            err(n, "unknown-table", f"table id '{tab}' not in manifest")

    report = {
        "deck": os.path.abspath(args.deck),
        "manifest": os.path.abspath(args.manifest),
        "generated_by": "fig_binding_lint.py",
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "verdict": "pass" if not errors else "error: illegal figure binding",
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(f"errors={len(errors)} warnings={len(warnings)} -> {args.report}")
    if errors:
        sys.stderr.write("error: illegal figure binding; deck must not be built "
                         "until all errors are resolved\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
