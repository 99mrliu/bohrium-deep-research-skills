#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""license_tiers.py — 数据源授权分级（绿/黄/红）。

内置分级规则表（人读版本见 rules/authorization_boundary.md，两者保持一致）：
  绿：官方公开库——可查询、可展示公开字段、可留存快照（须记录查询日期）；
  黄：需注明来源的开放聚合——可展示著录/摘要级信息，法律状态仅作线索，
      禁止批量留存全文；
  红：需登录/付费/许可受限库——禁止程序化抓取、禁止批量下载、禁止二次分发；
      只能人工查询后书写结论性描述，并给出绿色源替代与覆盖缺口标注。

输入：数据源清单 JSON：
  {"sources": [{"name": "...", "url": "...", "access": "public|login|paid|restricted"?, "note": "..."?}]}
输出：每个源的分级、可展示字段范围、留存限制、（红色源的）能力降级方案。

CLI：classify --sources FILE [--report OUT.json]
退出码：0 成功；1 输入非法。仅依赖标准库。
"""
import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 内置分级规则表（修改时请同步 rules/authorization_boundary.md）
# ---------------------------------------------------------------------------
TIER_RULES = [
    {
        "tier": "green",
        "label": "官方公开库",
        "patterns": [
            "cnipa", "国家知识产权局", "中国专利公布公告",
            "uspto", "patent center", "patent public search", "pair ",
            "epo", "espacenet", "european patent register", "全球专利索引",
            "wipo", "patentscope",
            "j-platpat", "kipris", "kripo",
            "official register", "官方登记", "官方公报", "gazette",
        ],
        "display_fields": "全部公开著录项目、权利要求书、说明书、法律状态快照；展示时必须标注来源与查询日期",
        "retention": "可留存公开字段快照与查询日期；快照须随结果注明'截至查询日期'",
        "degradation": None,
    },
    {
        "tier": "yellow",
        "label": "开放聚合（需注明来源）",
        "patterns": [
            "google patents", "lens.org", "the lens", "freepatentsonline",
            "patentguru", "sumobrain", "聚合", "转 载", "转载",
        ],
        "display_fields": "可展示著录项目与摘要级信息，必须注明'聚合来源，非官方登记'；法律状态只能作线索（leads_only）",
        "retention": "禁止批量留存全文；逐条引用须回到官方源复核",
        "degradation": "黄级源线索须用绿级官方源复核后方可升级为结论；复核失败则相关结论标 unknown",
    },
    {
        "tier": "red",
        "label": "许可受限（登录/付费/协议限制）",
        "patterns": [
            "derwent", "orbit", "questel", "lexisnexis", "totalpatent",
            "patentsight", "patsnap", "智慧芽", "incopat",
            "cnki", "万方", "wanfang", "维普",
            "subscription", "需登录", "付费",
        ],
        "display_fields": "仅可书写结论性描述；不得转载受限字段原文、不展示库内专有标引",
        "retention": "禁止程序化抓取、禁止批量下载、禁止二次分发；违反许可的访问一律不做",
        "degradation": ("能力降级方案：红色源禁止抓取时，改用绿色官方库（CNIPA/USPTO/EPO/WIPO）"
                        "逐项替代；红级源独有字段（如增值法律状态、引证分析）无法覆盖的，"
                        "在输出中显式标注'覆盖缺口：字段 X 暂无绿色源可核'，相关结论降级"
                        "并列入人工复核清单"),
    },
]

DEFAULT_TIER = {
    "tier": "yellow",
    "label": "未识别（从严按黄级处理）",
    "display_fields": "同黄级：仅著录/摘要级，注明来源",
    "retention": "禁止程序化抓取；仅人工浏览记录",
    "degradation": "未识别来源一律从严：禁止程序化抓取，结论须回到绿色官方源复核",
}


def classify_source(src):
    """对单个数据源分级。返回分级结果 dict。"""
    name = (src.get("name") or "").strip()
    url = (src.get("url") or "").strip()
    if not name and not url:
        return None
    haystack = (name + " " + url).casefold()
    access = (src.get("access") or "").strip().casefold()

    matched = None
    for rule in TIER_RULES:
        if any(p.casefold() in haystack for p in rule["patterns"]):
            matched = rule
            break

    # access 字段的硬约束：paid/login/restricted 至少按红级从严
    if access in ("paid", "login", "restricted"):
        red = next(r for r in TIER_RULES if r["tier"] == "green")  # placeholder guard
        red = TIER_RULES[2]
        if matched is None or matched["tier"] != "green":
            matched = red
        elif matched["tier"] == "green" and access in ("paid", "restricted"):
            # 官方源标绿但声明付费/受限：存在矛盾，从严降级并提示
            matched = dict(DEFAULT_TIER, note_extra="access=%s 与官方公开特征矛盾，从严处理" % access)

    rule = matched or DEFAULT_TIER
    result = {
        "name": name or url,
        "url": url or None,
        "tier": rule["tier"],
        "tier_label": rule["label"],
        "display_fields": rule["display_fields"],
        "retention": rule["retention"],
        "degradation": rule.get("degradation"),
        "access_declared": access or None,
    }
    if rule.get("note_extra"):
        result["note"] = rule["note_extra"]
    if matched is None:
        result["note"] = (result.get("note", "") + " 未匹配内置规则表，按黄级从严处理").strip()
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="数据源授权分级：绿/黄/红 + 能力降级方案")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap_c = sub.add_parser("classify", help="对数据源清单进行绿/黄/红分级")
    ap_c.add_argument("--sources", required=True, help="数据源清单 JSON 路径")
    ap_c.add_argument("--report", default=None, help="分级报告 JSON 输出路径")
    args = ap.parse_args(argv)

    p = Path(args.sources)
    if not p.exists():
        print("ERROR: 数据源清单不存在: %s" % args.sources, file=sys.stderr)
        return 1
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("ERROR: JSON 解析失败: %s" % e, file=sys.stderr)
        return 1
    srcs = data.get("sources")
    if not isinstance(srcs, list):
        print("ERROR: 清单必须含 sources 数组", file=sys.stderr)
        return 1

    results = []
    for src in srcs:
        r = classify_source(src if isinstance(src, dict) else {"name": str(src)})
        if r:
            results.append(r)

    green_alt = [r["name"] for r in results if r["tier"] == "green"]
    for r in results:
        if r["tier"] == "red":
            r["green_alternatives"] = green_alt or [
                "CNIPA 中国专利公布公告", "USPTO Patent Public Search",
                "EPO Espacenet / European Patent Register", "WIPO PATENTSCOPE"]
            r["coverage_gap"] = ("覆盖缺口标注要求：红色源 %s 的受限字段若绿色替代源无法覆盖，"
                                 "输出中必须逐字段标注缺口并把相关结论降级" % r["name"])

    tier_order = {"green": 0, "yellow": 1, "red": 2}
    for r in sorted(results, key=lambda x: tier_order.get(x["tier"], 3)):
        print("[%s] %s — %s" % (r["tier"].upper(), r["name"], r["tier_label"]))
        print("      可展示字段: %s" % r["display_fields"])
        print("      留存限制  : %s" % r["retention"])
        if r.get("degradation"):
            print("      降级方案  : %s" % r["degradation"])

    report = {
        "source_file": str(args.sources),
        "total": len(results),
        "tiers": {t: sum(1 for r in results if r["tier"] == t) for t in ("green", "yellow", "red")},
        "results": results,
    }
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n分级报告已写入: %s" % args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
