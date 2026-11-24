#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_report.py — 把 result.json 渲染成人读交付物。

  python3 render_report.py --result /app/output/result.json --outdir /app/output

产出：
  report.md   全字段结构化报告（始终生成）；
  summary.png 字段完成度与状态一览图（matplotlib 可用时生成；不可用则跳过并
              在 stdout 说明，不影响交付——JSON 才是契约成果）。
"""
import argparse
import json
import os

META_ORDER = ["case_id", "status", "limitations", "sources", "uncertainty",
              "change_records"]


def render_md(res):
    L = ["# 实验结果解释与异常分析 — 交付报告", "",
         "| 项 | 值 |", "|-|-|",
         "| case_id | `%s` |" % res.get("case_id"),
         "| status | **%s** |" % res.get("status"),
         "| 字段数 | %d |" % len([k for k in res if k not in META_ORDER]), ""]
    for k in [k for k in res if k not in META_ORDER]:
        L.append("## %s" % k)
        v = res[k]
        if isinstance(v, str):
            L.append(v if v else "_(未填写)_")
        else:
            L.append("```json\n" + json.dumps(v, ensure_ascii=False, indent=2)[:2000]
                     + "\n```")
        L.append("")
    L.append("## 元信息")
    for m in ("limitations", "sources", "uncertainty", "change_records"):
        L.append("### %s" % m)
        for it in res.get(m, []) or []:
            L.append("- %s" % it)
        L.append("")
    return "\n".join(L)


def render_png(res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    for pref in ("PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC",
                 "SimHei", "Microsoft YaHei", "Arial Unicode MS"):
        if pref in available:
            matplotlib.rcParams["font.family"] = pref
            matplotlib.rcParams["axes.unicode_minus"] = False
            break
    fields = [k for k in res if k not in META_ORDER]
    filled = [res[f] not in (None, "", [], {}) for f in fields]
    fig, ax = plt.subplots(figsize=(7, 0.5 * max(3, len(fields)) + 1))
    colors = ["#2e7d32" if x else "#c62828" for x in filled]
    ax.barh(range(len(fields)), [1] * len(fields), color=colors)
    ax.set_yticks(range(len(fields)))
    ax.set_yticklabels(fields, fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("case %s | status=%s | green=filled red=empty"
                 % (res.get("case_id"), res.get("status")), fontsize=10)
    for i, ok in enumerate(filled):
        ax.text(0.02, i, "filled" if ok else "EMPTY", va="center", fontsize=8,
                color="white")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    res = json.load(open(a.result, encoding="utf-8"))
    with open(os.path.join(a.outdir, "report.md"), "w", encoding="utf-8") as f:
        f.write(render_md(res))
    try:
        render_png(res, os.path.join(a.outdir, "summary.png"))
        print("[render] report.md + summary.png")
    except ImportError:
        print("[render] report.md（matplotlib 不可用，跳过 summary.png；"
              "契约成果 result.json 不受影响）")


if __name__ == "__main__":
    main()
