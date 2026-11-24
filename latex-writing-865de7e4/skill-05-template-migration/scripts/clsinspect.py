#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clsinspect.py — 目标模板接口解析与迁移计划生成（只读诊断，不修改任何稿件）。

用法：
    python3 clsinspect.py [--input /input] [--work /app/work]
                          [--manuscript PATH] [--cls PATH]

输入约定：
    case.json 缺失时遍历 --input 目录并如实降级（报告中注明）。
    未显式指定 --manuscript/--cls 时，在输入目录中启发式定位：
    .cls/.sty 中取第一个 .cls 为目标模板；.tex 中取含 \\documentclass 者为主稿。

产出（写入 <work>/migration/）：
    template_interface.md  模板 .cls/.sty 提供的接口清单（基类、自带宏包、
                           自定义命令/环境、文档选项、必填项及触发条件）
    migration_plan.md      章节映射表、必填项清单（已填/缺失/疑似占位）、
                           稿件与模板的宏包差异

本脚本只出计划，不改稿；所有编辑决策由 Agent 完成。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 正则工具 ----

RE_LOADCLASS = re.compile(r"\\LoadClass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
RE_REQUIRE = re.compile(r"\\RequirePackage\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
RE_NEWCMD = re.compile(
    r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z@]+)\}?\s*(?:\[(\d+)\])?")
RE_NEWENV = re.compile(r"\\(?:re)?newenvironment\*?\s*\{([^}]+)\}")
RE_DECLAREOPT = re.compile(r"\\DeclareOption\*?\s*\{([^}]+)\}")
RE_CLASSMSG = re.compile(
    r"\\(ClassError|ClassWarning|PackageError|PackageWarning)"
    r"\s*\{([^}]*)\}\s*\{([^}]*)\}", re.S)
RE_IFX_EMPTY = re.compile(
    r"\\ifx\s*\\([A-Za-z@]+)\s*\\@empty|\\ifx\s*\\@empty\s*\\([A-Za-z@]+)")
RE_IFUNDEF = re.compile(r"\\@ifundefined\{([^}]+)\}")
RE_BANNED = re.compile(
    r"\\@ifpackageloaded\{([^}]+)\}\s*\{[%\s]*\\(?:ClassError|PackageError)")

RE_DOCCLASS = re.compile(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
RE_USEPKG = re.compile(r"\\usepackage\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
RE_SECTION = re.compile(
    r"\\(part|chapter|section|subsection|subsubsection|paragraph)\*?"
    r"\s*(?:\[[^\]]*\])?\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
RE_BEGIN = re.compile(r"\\begin\{([^}]+)\}")
RE_LABEL = re.compile(r"\\label\{[^}]*\}")
RE_CITE = re.compile(r"\\cite\w*\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
RE_BIBSTYLE = re.compile(r"\\bibliographystyle\{([^}]+)\}")

PLACEHOLDER = re.compile(
    r"(?i)^[\s~]*(todo|tbd|to be filled|fixme|xxx+|\?+|placeholder|n/?a|"
    r"<[^>]*>|待填|待补充|占位)[\s~]*$")

SECTION_LEVELS = ["part", "chapter", "section", "subsection",
                  "subsubsection", "paragraph"]


def read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def strip_at(name):
    return name.lstrip("@")


def find_macro_arg(tex, name):
    """在稿件中查找 \\name{内容}，返回第一个参数文本；未找到返回 None。"""
    m = re.search(r"\\" + re.escape(name) + r"\s*(?:\[[^\]]*\])?\s*\{([^{}]*)",
                  tex)
    return m.group(1) if m else None


# ------------------------------------------------------------ 模板 .cls 解析 ----

def parse_class(path):
    text = read_text(path)
    info = {
        "file": str(path),
        "provides": None,
        "loadclass": None,
        "packages": [],       # [{name, options}]
        "commands": [],       # 类自定义命令（用户可见接口）
        "environments": [],
        "options": [],
        "required": [],       # [{macro, user_name, check, kind, message}]
        "banned_packages": [],
    }
    m = re.search(r"\\Provides(?:Class|Package)\{([^}]+)\}", text)
    if m:
        info["provides"] = m.group(1)
    m = RE_LOADCLASS.search(text)
    if m:
        info["loadclass"] = {"options": m.group(1) or "", "class": m.group(2)}
    for m in RE_REQUIRE.finditer(text):
        for name in m.group(2).split(","):
            info["packages"].append(
                {"name": name.strip(), "options": m.group(1) or ""})
    for m in RE_NEWCMD.finditer(text):
        name = m.group(1)
        if "@" in name:  # 内部命令不作用户接口展示
            continue
        info["commands"].append(
            {"name": name, "args": int(m.group(2) or 0)})
    info["environments"] = sorted({m.group(1)
                                   for m in RE_NEWENV.finditer(text)})
    opts = set()
    for m in re.finditer(r"\\DeclareOption(\*?)\s*\{([^}]+)\}", text):
        if m.group(1) == "*":
            opts.add("(通配：未识别选项透传给基类)")
        elif "\\" not in m.group(2):
            opts.add(m.group(2))
    info["options"] = sorted(opts)
    info["banned_packages"] = sorted({m.group(1).strip()
                                      for m in RE_BANNED.finditer(text)})
    # 必填项：\ClassError/\ClassWarning 之前窗口内的 \ifx\<mac>\@empty 等判空
    for m in RE_CLASSMSG.finditer(text):
        window = text[max(0, m.start() - 400):m.start()]
        macro = None
        mm = list(RE_IFX_EMPTY.finditer(window))
        if mm:
            macro = mm[-1].group(1) or mm[-1].group(2)
        else:
            mm = list(RE_IFUNDEF.finditer(window))
            if mm:
                macro = mm[-1].group(1)
        message = re.sub(r"\s+", " ", m.group(3)).strip()
        info["required"].append({
            "macro": macro or "(未识别)",
            "user_name": strip_at(macro) if macro else "(未识别)",
            "kind": m.group(1),
            "message": message,
        })
    return info


# ------------------------------------------------------------ 稿件 .tex 解析 ----

def parse_manuscript(path):
    text = read_text(path)
    lines = text.splitlines()
    info = {
        "file": str(path),
        "documentclass": None,
        "packages": [],   # [{name, options, line}]
        "sections": [],   # [{level, title, line}]
        "floats": {},
        "labels": len(RE_LABEL.findall(text)),
        "citations": sorted({k.strip() for m in RE_CITE.finditer(text)
                             for k in m.group(1).split(",")}),
        "bibstyle": (RE_BIBSTYLE.search(text).group(1)
                     if RE_BIBSTYLE.search(text) else None),
        "has_thebibliography": "\\begin{thebibliography}" in text,
    }
    m = RE_DOCCLASS.search(text)
    if m:
        info["documentclass"] = {"options": m.group(1) or "",
                                 "class": m.group(2)}
    for i, line in enumerate(lines, 1):
        for m in RE_USEPKG.finditer(line):
            for name in m.group(2).split(","):
                info["packages"].append({"name": name.strip(),
                                         "options": m.group(1) or "",
                                         "line": i})
        m = RE_SECTION.search(line)
        if m:
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            info["sections"].append({"level": m.group(1),
                                     "title": title, "line": i})
    for name in RE_BEGIN.findall(text):
        if name in ("document", "abstract", "tabular", "tabularx",
                    "thebibliography") or name.endswith("*") and \
                name[:-1] in ("tabular",):
            continue
        info["floats"][name] = info["floats"].get(name, 0) + 1
    return info


# ------------------------------------------------------------ 输入定位 ---------

def load_case(input_dir):
    p = Path(input_dir) / "case.json"
    if p.is_file():
        try:
            return json.loads(read_text(p)), []
        except json.JSONDecodeError as exc:
            return None, ["case.json 解析失败：%s（已降级为目录扫描）" % exc]
    files = sorted(str(f.relative_to(input_dir))
                   for f in Path(input_dir).rglob("*") if f.is_file())
    return None, ["case.json 缺失，已遍历输入目录降级；发现文件：%s"
                  % (", ".join(files) if files else "（空）")]


def locate_inputs(input_dir, manuscript, cls):
    notes = []
    input_dir = Path(input_dir)
    if cls is None:
        cands = sorted(input_dir.rglob("*.cls")) or \
            sorted(input_dir.rglob("*.sty"))
        if cands:
            cls = cands[0]
            notes.append("未指定 --cls，取 %s 为目标模板" % cls)
    if manuscript is None:
        for tex in sorted(input_dir.rglob("*.tex")):
            if RE_DOCCLASS.search(read_text(tex)):
                manuscript = tex
                notes.append("未指定 --manuscript，取 %s 为主稿" % tex)
                break
    return manuscript, cls, notes


# ------------------------------------------------------------ 报告生成 ---------

def write_interface(cls_info, out_path, degrade_notes):
    L = ["# 模板接口清单（template_interface）", ""]
    for n in degrade_notes:
        L.append("> 降级说明：%s" % n)
    if degrade_notes:
        L.append("")
    if cls_info is None:
        L.append("**未找到目标模板 .cls/.sty，无法解析接口。**")
        L.append("")
        L.append("后续步骤只能依赖 task.md 的文字要求，Agent 需在 "
                 "uncertainty 中注明模板缺失。")
        out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
        return
    L.append("- 模板文件：`%s`" % cls_info["file"])
    L.append("- 标识：`%s`" % (cls_info["provides"] or "未知"))
    if cls_info["loadclass"]:
        lc = cls_info["loadclass"]
        L.append("- 基类：\\LoadClass[%s]{%s}" % (lc["options"], lc["class"]))
    L.append("")
    L.append("## 类自带宏包（稿件侧重复加载即构成差异点）")
    L.append("")
    L.append("| 宏包 | 选项 |")
    L.append("| --- | --- |")
    for p in cls_info["packages"]:
        L.append("| %s | %s |" % (p["name"], p["options"] or "—"))
    if not cls_info["packages"]:
        L.append("| （无） | |")
    L.append("")
    L.append("## 类自定义命令（用户接口）")
    L.append("")
    L.append("| 命令 | 参数个数 |")
    L.append("| --- | --- |")
    for c in cls_info["commands"]:
        L.append("| \\%s | %d |" % (c["name"], c["args"]))
    if not cls_info["commands"]:
        L.append("| （无） | |")
    L.append("")
    L.append("## 类自定义环境")
    L.append("")
    L.append(", ".join("`%s`" % e for e in cls_info["environments"])
             or "（无）")
    L.append("")
    L.append("## 文档选项")
    L.append("")
    L.append(", ".join("`%s`" % o for o in cls_info["options"]) or "（无）")
    L.append("")
    L.append("## 必填项检查（类在编译期触发 \\ClassError / \\ClassWarning）")
    L.append("")
    L.append("| 用户命令 | 内部宏 | 触发类型 | 报错信息 |")
    L.append("| --- | --- | --- | --- |")
    for r in cls_info["required"]:
        L.append("| \\%s | \\%s | %s | %s |"
                 % (r["user_name"], r["macro"], r["kind"], r["message"]))
    if not cls_info["required"]:
        L.append("| （未检出显式必填项）| | | |")
    L.append("")
    L.append("## 模板禁用宏包")
    L.append("")
    L.append(", ".join("`%s`" % b for b in cls_info["banned_packages"])
             or "（未检出）")
    L.append("")
    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")


def required_status(cls_info, ms_text):
    """必填项清单：已填 / 疑似占位 / 缺失。"""
    rows = []
    if not cls_info:
        return rows
    seen = set()
    for r in cls_info["required"]:
        name = r["user_name"]
        if name in seen or name == "(未识别)":
            continue
        seen.add(name)
        val = find_macro_arg(ms_text, name)
        if val is None:
            status = "缺失"
        elif not val.strip():
            status = "缺失（空调用）"
        elif PLACEHOLDER.match(val):
            status = "疑似占位"
        else:
            status = "已填"
        rows.append({"name": name, "status": status,
                     "value": (val or "").strip()})
    return rows


def write_plan(cls_info, ms_info, req_rows, out_path):
    L = ["# 迁移计划（migration_plan，只读诊断，改动由 Agent 决策执行）", ""]
    if ms_info is None:
        L.append("**未找到主稿 .tex，无法生成迁移计划。**")
        out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
        return
    dc = ms_info["documentclass"] or {"class": "?", "options": ""}
    L.append("## 稿件现状")
    L.append("")
    L.append("- 主稿：`%s`" % ms_info["file"])
    L.append("- 当前类：\\documentclass[%s]{%s}" % (dc["options"], dc["class"]))
    if cls_info:
        L.append("- 目标模板：`%s`" % cls_info["file"])
    L.append("- \\label 数：%d；\\cite 键：%s"
             % (ms_info["labels"],
                ", ".join("`%s`" % k for k in ms_info["citations"]) or "无"))
    L.append("- 文献方式：%s"
             % ("thebibliography 环境" if ms_info["has_thebibliography"]
                else ("\\bibliographystyle{%s}" % ms_info["bibstyle"]
                      if ms_info["bibstyle"] else "未检出")))
    floats = ", ".join("%s×%d" % (k, v)
                       for k, v in sorted(ms_info["floats"].items()))
    L.append("- 浮动体/环境统计：%s" % (floats or "无"))
    L.append("")
    L.append("## 章节结构映射表（默认同级别直映，Agent 需逐条确认）")
    L.append("")
    L.append("| 原稿行号 | 原稿命令 | 原稿标题 | 目标命令（建议） | 状态 |")
    L.append("| --- | --- | --- | --- | --- |")
    for s in ms_info["sections"]:
        L.append("| %d | \\%s | %s | \\%s | 待 Agent 确认 |"
                 % (s["line"], s["level"], s["title"], s["level"]))
    if not ms_info["sections"]:
        L.append("| — | （原稿未使用标准章节命令）| | | |")
    L.append("")
    L.append("## 模板必填项落实清单")
    L.append("")
    L.append("| 必填字段 | 当前状态 | 当前值 |")
    L.append("| --- | --- | --- |")
    for r in req_rows:
        L.append("| \\%s | %s | %s |"
                 % (r["name"], r["status"], r["value"] or "—"))
    if not req_rows:
        L.append("| （目标模板未检出必填项，或无模板）| | |")
    L.append("")
    L.append("## 宏包差异（稿件 vs 模板类自带）")
    L.append("")
    L.append("| 稿件宏包 | 稿件选项 | 模板是否已提供 | 模板选项 | 建议 |")
    L.append("| --- | --- | --- | --- | --- |")
    cls_pkgs = {p["name"]: p["options"] for p in
                (cls_info["packages"] if cls_info else [])}
    for p in ms_info["packages"]:
        if p["name"] in cls_pkgs:
            same = cls_pkgs[p["name"]] == p["options"]
            advice = ("删除稿件侧重复加载" if same else
                      "选项不一致，存在 Option clash 风险：删除稿件侧调用，"
                      "如需改选项用 \\PassOptionsToPackage")
            L.append("| %s | %s | 是 | %s | %s |"
                     % (p["name"], p["options"] or "—",
                        cls_pkgs[p["name"]] or "—", advice))
        else:
            L.append("| %s | %s | 否 | — | 保留与否由 Agent 判断"
                     "（先跑 pkgconflict.py 查合规） |"
                     % (p["name"], p["options"] or "—"))
    if not ms_info["packages"]:
        L.append("| （稿件未显式加载宏包）| | | | |")
    L.append("")
    L.append("## 下一步")
    L.append("")
    L.append("1. 运行 `pkgconflict.py` 获取加载顺序与冲突对的处置建议；")
    L.append("2. Agent 依据本计划与 task.md 执行迁移编辑（脚本不改稿）；")
    L.append("3. 迁移完成后运行 `finalize.py` 做合规检查、编译验证与最小 diff。")
    L.append("")
    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------ main -------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="模板接口解析与迁移计划（只读）")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--manuscript", default=None)
    ap.add_argument("--cls", default=None)
    args = ap.parse_args(argv)

    case, degrade = load_case(args.input)
    manuscript, cls, notes = locate_inputs(args.input, args.manuscript,
                                           args.cls)
    degrade.extend(notes)

    out_dir = Path(args.work) / "migration"
    out_dir.mkdir(parents=True, exist_ok=True)

    cls_info = parse_class(cls) if cls and Path(cls).is_file() else None
    if cls and not Path(cls).is_file():
        degrade.append("指定的模板文件不存在：%s" % cls)
    ms_info = parse_manuscript(manuscript) if manuscript and \
        Path(manuscript).is_file() else None
    if manuscript and not Path(manuscript).is_file():
        degrade.append("指定的稿件文件不存在：%s" % manuscript)

    write_interface(cls_info, out_dir / "template_interface.md", degrade)
    ms_text = read_text(manuscript) if ms_info else ""
    req_rows = required_status(cls_info, ms_text)
    write_plan(cls_info, ms_info, req_rows, out_dir / "migration_plan.md")

    print("[clsinspect] case_id=%s" %
          (case.get("case_id") if isinstance(case, dict) else "（无 case.json）"))
    print("[clsinspect] 模板：%s" % (cls or "未找到"))
    print("[clsinspect] 主稿：%s" % (manuscript or "未找到"))
    if cls_info:
        print("[clsinspect] 必填项：%s"
              % (", ".join("\\" + r["user_name"] for r in cls_info["required"])
                 or "无"))
    for r in req_rows:
        print("[clsinspect]   \\%s -> %s" % (r["name"], r["status"]))
    print("[clsinspect] 报告已写入 %s" % out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
