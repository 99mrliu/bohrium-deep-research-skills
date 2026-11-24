#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pkgconflict.py — 宏包合规检查（只给处置建议，不自动改导言区）。

用法：
    python3 pkgconflict.py [--input /input] [--work /app/work]
                           [--manuscript PATH] [--cls PATH]

检查项：
    1. 加载顺序规则（hyperref 最后、cleveref 在 hyperref 之后等，
       规则表在 references/package-conflicts.md，脚本直接解析其中的表格）；
    2. 已知冲突对（natbib vs cite 等，同表）；
    3. 与模板类 \\RequirePackage 重复的宏包（含选项不一致风险）；
    4. 模板类显式禁用的宏包（\\@ifpackageloaded + \\ClassError 模式）。

产出：<work>/migration/conflicts.md，每条附证据（文件:行号）与处置建议。
"""
import argparse
import re
import sys
from pathlib import Path

RE_DOCCLASS = re.compile(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
RE_USEPKG = re.compile(r"\\usepackage\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
RE_REQUIRE = re.compile(r"\\RequirePackage\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
RE_BANNED = re.compile(
    r"\\@ifpackageloaded\{([^}]+)\}\s*\{[%\s]*\\(?:ClassError|PackageError)")

# 规则表文件缺失时的最小内置兜底（与 references/package-conflicts.md 保持一致）
FALLBACK_ORDER = [
    {"package": "hyperref", "constraint": "last_except", "peers": "cleveref",
     "note": "hyperref 应在稿件显式加载的宏包中最后出现（少数例外除外）"},
    {"package": "cleveref", "constraint": "after", "peers": "hyperref",
     "note": "cleveref 必须在 hyperref 之后加载"},
    {"package": "cleveref", "constraint": "after", "peers": "amsmath",
     "note": "同时使用 amsmath 时，cleveref 应在其后"},
]
FALLBACK_PAIRS = [
    {"a": "natbib", "b": "cite", "severity": "error",
     "advice": "两套引用机制互斥，按模板指定二选一"},
]


# ------------------------------------------------------------ 规则表解析 -------

def parse_md_table(lines, start):
    """从 lines[start] 起的 markdown 表格解析为 dict 列表。"""
    rows = []
    i = start
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if not all(re.fullmatch(r":?-{2,}:?", c or "---") for c in cells):
            rows.append(cells)
        i += 1
    if len(rows) < 2:
        return []
    header = rows[0]
    return [dict(zip(header, r)) for r in rows[1:]]


def load_rules(refs_path):
    """从 references/package-conflicts.md 读取两张机器可读表。"""
    order, pairs, source = None, None, None
    p = Path(refs_path)
    if p.is_file():
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if line.startswith("## ") and "加载顺序规则" in line:
                j = i + 1
                while j < len(lines) and not lines[j].lstrip().startswith("|"):
                    j += 1
                order = parse_md_table(lines, j)
            if line.startswith("## ") and "已知冲突对" in line:
                j = i + 1
                while j < len(lines) and not lines[j].lstrip().startswith("|"):
                    j += 1
                pairs = parse_md_table(lines, j)
        if order and pairs:
            source = str(p)
    if not order:
        order = FALLBACK_ORDER
    if not pairs:
        pairs = FALLBACK_PAIRS
    return order, pairs, source


# ------------------------------------------------------------ 稿件/类解析 ------

def manuscript_packages(path):
    """按出现顺序返回 [{name, options, line, index}]。"""
    pkgs, idx = [], 0
    for i, line in enumerate(
            Path(path).read_text(encoding="utf-8", errors="replace")
            .splitlines(), 1):
        if RE_DOCCLASS.search(line):
            continue
        for m in RE_USEPKG.finditer(line):
            for name in m.group(2).split(","):
                pkgs.append({"name": name.strip(),
                             "options": m.group(1) or "",
                             "line": i, "index": idx})
                idx += 1
    return pkgs


def class_packages(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    pkgs = {}
    for m in RE_REQUIRE.finditer(text):
        for name in m.group(2).split(","):
            pkgs[name.strip()] = m.group(1) or ""
    banned = sorted({m.group(1).strip() for m in RE_BANNED.finditer(text)})
    return pkgs, banned


def locate(input_dir, manuscript, cls):
    notes = []
    input_dir = Path(input_dir)
    if cls is None:
        cands = sorted(input_dir.rglob("*.cls")) or \
            sorted(input_dir.rglob("*.sty"))
        if cands:
            cls = cands[0]
            notes.append("未指定 --cls，取 %s" % cls)
    if manuscript is None:
        for tex in sorted(input_dir.rglob("*.tex")):
            if RE_DOCCLASS.search(tex.read_text(encoding="utf-8",
                                                errors="replace")):
                manuscript = tex
                notes.append("未指定 --manuscript，取 %s" % tex)
                break
    return manuscript, cls, notes


# ------------------------------------------------------------ 检查逻辑 ---------

def check_order(pkgs, order_rules):
    issues = []
    pos = {p["name"]: p for p in pkgs}
    for rule in order_rules:
        name = rule.get("package", "").strip()
        if name not in pos:
            continue
        constraint = rule.get("constraint", "").strip()
        peers = [x.strip() for x in rule.get("peers", "").split(",")
                 if x.strip()]
        me = pos[name]
        if constraint == "last_except":
            later = [p for p in pkgs
                     if p["index"] > me["index"] and p["name"] not in peers]
            if later:
                issues.append({
                    "type": "加载顺序", "severity": "warning",
                    "evidence": "%s 在第 %d 行加载，但其后仍加载 %s"
                                % (name, me["line"],
                                   ", ".join("%s(行%d)" % (p["name"],
                                                          p["line"])
                                             for p in later)),
                    "advice": "将 %s 移到稿件宏包清单末尾%s。规则：%s"
                              % (name,
                                 ("（例外允许在其后：%s）" % ", ".join(peers))
                                 if peers else "",
                                 rule.get("note", "")),
                })
        elif constraint in ("after", "before"):
            for peer in peers:
                if peer not in pos:
                    continue
                bad = (constraint == "after"
                       and me["index"] < pos[peer]["index"]) or \
                      (constraint == "before"
                       and me["index"] > pos[peer]["index"])
                if bad:
                    want = "之后" if constraint == "after" else "之前"
                    issues.append({
                        "type": "加载顺序", "severity": "warning",
                        "evidence": "%s(行%d) 与 %s(行%d) 的相对顺序违规"
                                    % (name, me["line"], peer,
                                       pos[peer]["line"]),
                        "advice": "%s 应加载在 %s %s。规则：%s"
                                  % (name, peer, want,
                                     rule.get("note", "")),
                    })
    return issues


def check_pairs(pkgs, pair_rules):
    names = {p["name"] for p in pkgs}
    issues = []
    for rule in pair_rules:
        a, b = rule.get("package_a", "").strip(), \
            rule.get("package_b", "").strip()
        if a in names and b in names:
            issues.append({
                "type": "已知冲突对",
                "severity": rule.get("severity", "warning").strip()
                or "warning",
                "evidence": "稿件同时加载 %s 与 %s" % (a, b),
                "advice": rule.get("advice", ""),
            })
    return issues


def check_class_overlap(pkgs, cls_pkgs, banned, ms_path):
    issues = []
    for p in pkgs:
        if p["name"] in banned:
            issues.append({
                "type": "模板禁用宏包", "severity": "error",
                "evidence": "%s:%d 加载 %s，而目标模板显式禁用该宏包"
                            % (ms_path, p["line"], p["name"]),
                "advice": "迁移稿中移除 %s，并改用模板自带机制实现同等效果"
                          % p["name"],
            })
        elif p["name"] in cls_pkgs:
            same = cls_pkgs[p["name"]] == p["options"]
            issues.append({
                "type": "与模板类重复",
                "severity": "warning" if same else "error",
                "evidence": "%s:%d 加载 %s[%s]，模板类已 "
                            "\\RequirePackage[%s]{%s}"
                            % (ms_path, p["line"], p["name"], p["options"],
                               cls_pkgs[p["name"]], p["name"]),
                "advice": ("迁移稿中删除稿件侧重复加载"
                           if same else
                           "选项不一致，迁移后将触发 Option clash：删除稿件侧"
                           "调用；确需不同选项时改用 \\PassOptionsToPackage"
                           "（须置于 \\documentclass 之前）"),
            })
    return issues


# ------------------------------------------------------------ main -------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="宏包合规检查（只给建议）")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--manuscript", default=None)
    ap.add_argument("--cls", default=None)
    ap.add_argument("--rules", default=None,
                    help="规则表 md，默认取 bundle 内 references/"
                         "package-conflicts.md")
    args = ap.parse_args(argv)

    rules_path = args.rules or (
        Path(__file__).resolve().parents[1]
        / "references" / "package-conflicts.md")
    order_rules, pair_rules, rules_src = load_rules(rules_path)

    manuscript, cls, notes = locate(args.input, args.manuscript, args.cls)
    out_dir = Path(args.work) / "migration"
    out_dir.mkdir(parents=True, exist_ok=True)

    L = ["# 宏包合规检查报告（conflicts）", ""]
    L.append("> 本报告只给处置建议；导言区的任何改动由 Agent 判断并执行。")
    L.append("")
    for n in notes:
        L.append("> 降级说明：%s" % n)
    if notes:
        L.append("")
    L.append("- 规则表来源：%s"
             % (rules_src or "内置兜底表（未找到 references/"
                "package-conflicts.md，已降级）"))
    L.append("")

    issues = []
    if manuscript is None or not Path(manuscript).is_file():
        L.append("**未找到主稿 .tex，无法检查。**")
    else:
        ms_path = str(manuscript)
        pkgs = manuscript_packages(manuscript)
        cls_pkgs, banned = ({}, [])
        if cls and Path(cls).is_file():
            cls_pkgs, banned = class_packages(cls)
        L.append("- 稿件：`%s`（显式加载 %d 个宏包）"
                 % (ms_path, len(pkgs)))
        L.append("- 模板类：`%s`" % (cls or "未找到，跳过类相关检查"))
        L.append("")
        issues += check_order(pkgs, order_rules)
        issues += check_pairs(pkgs, pair_rules)
        issues += check_class_overlap(pkgs, cls_pkgs, banned, ms_path)

        L.append("## 问题清单（共 %d 条）" % len(issues))
        L.append("")
        if not issues:
            L.append("未发现问题。")
        for i, it in enumerate(issues, 1):
            L.append("### %d. [%s][%s]" % (i, it["type"], it["severity"]))
            L.append("")
            L.append("- 证据：%s" % it["evidence"])
            L.append("- 处置建议：%s" % it["advice"])
            L.append("")

    out = out_dir / "conflicts.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("[pkgconflict] 发现问题 %d 条，报告已写入 %s" % (len(issues), out))
    for it in issues:
        print("[pkgconflict]   [%s][%s] %s"
              % (it["type"], it["severity"], it["evidence"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
