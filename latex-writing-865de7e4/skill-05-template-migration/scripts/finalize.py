#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize.py — 迁移完成后的合规检查、编译验证、最小 diff 与 result.json 装配。

用法：
    python3 finalize.py [--input /input] [--work /app/work] [--output /app/output]
                        [--original PATH] [--migrated PATH] [--cls PATH]
                        [--timeout 60] [--passes 2]

检查内容：
    1. 模板必填字段：非空且非占位（缺失/占位 -> 判不合规，不放行）；
    2. 章节映射落实：原稿全部章节标题在迁移稿中均有对应；
    3. 编译验证：真实调用 pdflatex，有界两轮（默认每轮 60s 上限）；
       未探测到 pdflatex 时诚实降级标注，不假装成功；
    4. 最小 diff：原稿与迁移稿正文段落级对齐，忽略纯命令/空白差异，
       任何实际文字改动逐条列出供 Agent 确认意图保留。

交付（写入 --output）：
    迁移稿源码（可继续编辑）、目标模板副本（若存在）、
    compliance.json / compliance.md、intent_diff.md、result.json。

契约归一化支持四种历史方言：{字段: {type, required}}、自然语言描述、
JSON Schema、字段名列表。缺材料的契约字段给诚实的 null 并在
uncertainty 中说明，禁止填充编造值。
"""
import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- 正则 ---------

RE_DOCCLASS = re.compile(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
RE_CLASSMSG = re.compile(
    r"\\(ClassError|ClassWarning)\s*\{([^}]*)\}\s*\{([^}]*)\}", re.S)
RE_IFX_EMPTY = re.compile(
    r"\\ifx\s*\\([A-Za-z@]+)\s*\\@empty|\\ifx\s*\\@empty\s*\\([A-Za-z@]+)")
RE_IFUNDEF = re.compile(r"\\@ifundefined\{([^}]+)\}")
RE_SECTION = re.compile(
    r"\\(part|chapter|section|subsection|subsubsection|paragraph)\*?"
    r"\s*(?:\[[^\]]*\])?\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
RE_CMD = re.compile(r"\\[a-zA-Z@]+\*?")

PLACEHOLDER = re.compile(
    r"(?i)^[\s~]*(todo|tbd|to be filled|fixme|xxx+|\?+|placeholder|n/?a|"
    r"<[^>]*>|待填|待补充|占位)[\s~]*$")


def read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


# ------------------------------------------------------------ case 与契约 ------

def load_case(input_dir):
    p = Path(input_dir) / "case.json"
    if p.is_file():
        try:
            return json.loads(read_text(p)), []
        except json.JSONDecodeError as exc:
            return {}, ["case.json 解析失败：%s" % exc]
    files = sorted(str(f.relative_to(input_dir))
                   for f in Path(input_dir).rglob("*") if f.is_file())
    return {}, ["case.json 缺失，已遍历输入目录降级；发现文件：%s"
                % (", ".join(files) if files else "（空）")]


def normalize_contract(raw):
    """归一化四种 output_contract 方言 -> (fields, note)。

    fields: [{"name": str, "type": str|None, "required": bool|None}]
    """
    if raw is None:
        return [], "case.json 未声明 output_contract"
    if isinstance(raw, dict):
        if isinstance(raw.get("properties"), dict):  # JSON Schema
            req = set(raw.get("required") or [])
            return ([{"name": k,
                      "type": (v or {}).get("type") if isinstance(v, dict)
                      else None,
                      "required": k in req}
                     for k, v in raw["properties"].items()],
                    "JSON Schema 方言")
        if raw and all(isinstance(v, dict) and
                       ("type" in v or "required" in v)
                       for v in raw.values()):
            return ([{"name": k, "type": v.get("type"),
                      "required": bool(v.get("required"))}
                     for k, v in raw.items()], "{type, required} 方言")
        return ([{"name": k, "type": None, "required": None}
                 for k in raw], "键名即字段方言")
    if isinstance(raw, list):
        return ([{"name": str(x), "type": None, "required": None}
                 for x in raw], "字段名列表方言")
    if isinstance(raw, str):
        fields = []
        for line in raw.splitlines():
            m = re.match(r"\s*[-*•]?\s*`?([A-Za-z_][\w.-]*)`?"
                         r"\s*[:：—-]\s*(.+)", line)
            if m:
                fields.append({"name": m.group(1), "type": None,
                               "required": None})
        note = ("自然语言方言（按 `- 字段名: 描述` 启发式提取，需人工核对）"
                if fields else
                "自然语言方言，未能提取字段名，原样保留于 "
                "result.contract_raw")
        return fields, note
    return [], "未知方言，原样保留于 result.contract_raw"


def fill_field(name, ctx):
    """按字段名语义把契约字段映射到真实产物；无法映射返回 None（诚实空值）。"""
    n = name.lower()
    if any(k in n for k in ("migrat", "manuscript", "source")):
        return ctx.get("migrated_out")
    if "complian" in n:
        return ctx.get("compliance_out")
    if "diff" in n or "intent" in n:
        return ctx.get("diff_out")
    if "compile" in n or "pdf" in n:
        return ctx.get("compile_ok")
    if "plan" in n:
        return ctx.get("plan_out")
    return None


# ------------------------------------------------------------ 合规检查 ---------

def class_required_fields(cls_path):
    """从模板类解析必填项（与 clsinspect 同一启发式，各自独立实现）。"""
    if not cls_path or not Path(cls_path).is_file():
        return []
    text = read_text(cls_path)
    out, seen = [], set()
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
        if not macro:
            continue
        name = macro.lstrip("@")
        if name not in seen:
            seen.add(name)
            out.append({"name": name,
                        "message": re.sub(r"\s+", " ", m.group(3)).strip()})
    return out


def check_required(required, migrated_text):
    rows = []
    for r in required:
        m = re.search(r"\\" + re.escape(r["name"]) +
                      r"\s*(?:\[[^\]]*\])?\s*\{([^{}]*)", migrated_text)
        if m is None:
            status, ok = "缺失", False
        elif not m.group(1).strip():
            status, ok = "缺失（空调用）", False
        elif PLACEHOLDER.match(m.group(1)):
            status, ok = "疑似占位", False
        else:
            status, ok = "已填", True
        rows.append({"field": r["name"], "status": status, "ok": ok,
                     "value": (m.group(1).strip() if m else "")})
    return rows


def norm_title(t):
    t = RE_CMD.sub("", t)
    return re.sub(r"\s+", " ", t.replace("{", "").replace("}", "")) \
        .strip().lower()


def check_sections(original_text, migrated_text):
    orig = [norm_title(m.group(2)) for m in RE_SECTION.finditer(original_text)]
    mig = {norm_title(m.group(2)) for m in RE_SECTION.finditer(migrated_text)}
    missing = [t for t in orig if t not in mig]
    return {"original_count": len(orig), "missing": missing,
            "ok": not missing}


# ------------------------------------------------------------ 编译验证 ---------

def compile_check(migrated, cls, work_dir, timeout, passes):
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        return {"status": "skipped", "ok": None, "pages": None,
                "reason": "未探测到 pdflatex，编译验证诚实降级（未执行）",
                "passes": 0, "errors": []}
    build = Path(work_dir) / "build"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)
    migrated = Path(migrated)
    shutil.copy2(migrated, build / migrated.name)
    if cls and Path(cls).is_file():
        shutil.copy2(cls, build / Path(cls).name)
    for ext in ("*.sty", "*.bst", "*.bib", "*.cls"):
        for f in migrated.parent.glob(ext):
            if not (build / f.name).exists():
                shutil.copy2(f, build / f.name)
    errors, pages, ran = [], None, 0
    for rnd in range(1, max(1, passes) + 1):
        try:
            proc = subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "-halt-on-error",
                 migrated.name],
                cwd=str(build), timeout=timeout,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            ran += 1
            out = proc.stdout.decode("utf-8", errors="replace")
            if proc.returncode != 0:
                errors += [ln for ln in out.splitlines()
                           if ln.startswith("!")][:5]
                break
        except subprocess.TimeoutExpired:
            errors.append("第 %d 轮编译超时（上限 %ds）" % (rnd, timeout))
            break
    pdf = build / (migrated.stem + ".pdf")
    log = build / (migrated.stem + ".log")
    if pdf.is_file() and log.is_file():
        m = re.search(r"Output written on .+ \((\d+) page",
                      read_text(log))
        if m:
            pages = int(m.group(1))
    ok = pdf.is_file() and not errors
    return {"status": "ran", "ok": ok, "pages": pages,
            "reason": "" if ok else "编译失败或存在错误",
            "passes": ran, "errors": errors,
            "pdf_pages_note": ("实际运行生成了 %d 页 PDF（构建目录内，"
                               "未随包提交）" % pages) if pages else ""}


# ------------------------------------------------------------ 最小 diff --------

def strip_comments(text):
    out = []
    for line in text.splitlines():
        buf, i = [], 0
        while i < len(line):
            c = line[i]
            if c == "%" and (i == 0 or line[i - 1] != "\\"):
                break
            buf.append(c)
            i += 1
        out.append("".join(buf))
    return "\n".join(out)


def extract_body(text):
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", text, re.S)
    return m.group(1) if m else text


def normalize_para(p):
    p = RE_CMD.sub("", p)
    p = p.replace("{", "").replace("}", "").replace("~", " ")
    p = re.sub(r"\\[$&%#_{}]", "", p)
    return re.sub(r"\s+", " ", p).strip()


def paragraphs(text):
    body = extract_body(strip_comments(text))
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def intent_diff(original_text, migrated_text):
    op = paragraphs(original_text)
    mp = paragraphs(migrated_text)
    on = [normalize_para(p) for p in op]
    mn = [normalize_para(p) for p in mp]
    sm = difflib.SequenceMatcher(None, on, mn, autojunk=False)
    equal, changed, added, removed = 0, [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            equal += i2 - i1
        elif tag == "replace":
            for a, b in zip(op[i1:i2], mp[j1:j2]):
                changed.append({"original": re.sub(r"\s+", " ", a).strip(),
                                "migrated": re.sub(r"\s+", " ", b).strip()})
            if (i2 - i1) > (j2 - j1):
                removed += [re.sub(r"\s+", " ", x).strip()
                            for x in op[i1 + (j2 - j1):i2]]
            elif (j2 - j1) > (i2 - i1):
                added += [re.sub(r"\s+", " ", x).strip()
                          for x in mp[j1 + (i2 - i1):j2]]
        elif tag == "delete":
            removed += [re.sub(r"\s+", " ", x).strip() for x in op[i1:i2]]
        elif tag == "insert":
            added += [re.sub(r"\s+", " ", x).strip() for x in mp[j1:j2]]
    return {"original_paragraphs": len(op), "migrated_paragraphs": len(mp),
            "unchanged": equal, "changed": changed,
            "added": added, "removed": removed,
            "text_changes": len(changed) + len(added) + len(removed)}


def write_intent_diff(rep, out_path):
    L = ["# 正文意图最小 diff（intent_diff）", ""]
    L.append("段落级对齐；比较前已剥除注释、LaTeX 命令与多余空白，"
             "因此纯命令/空白差异不计入文字改动。")
    L.append("")
    L.append("- 原稿正文段落：%d；迁移稿正文段落：%d"
             % (rep["original_paragraphs"], rep["migrated_paragraphs"]))
    L.append("- 完全一致段落：%d" % rep["unchanged"])
    L.append("- 实际文字改动：%d（改 %d / 增 %d / 删 %d）"
             % (rep["text_changes"], len(rep["changed"]),
                len(rep["added"]), len(rep["removed"])))
    L.append("")
    if rep["text_changes"] == 0:
        L.append("**结论：正文零文字改动，原文意图保留。**")
        L.append("")
        out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
        return
    L.append("**以下改动需 Agent 逐条确认是否为有意为之：**")
    L.append("")
    for i, c in enumerate(rep["changed"], 1):
        L.append("## 改动 %d" % i)
        L.append("")
        L.append("- 原稿：%s" % c["original"])
        L.append("- 迁移稿：%s" % c["migrated"])
        L.append("")
    for x in rep["added"]:
        L.append("- 【新增段落】%s" % x)
    for x in rep["removed"]:
        L.append("- 【删除段落】%s" % x)
    if rep["added"] or rep["removed"]:
        L.append("")
    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------ 输入定位 ---------

def locate_tex(input_dir, explicit, prefer_migrated):
    if explicit:
        return explicit, None
    cands = [t for t in sorted(Path(input_dir).rglob("*.tex"))
             if RE_DOCCLASS.search(read_text(t))]
    if not cands:
        return None, "未在输入目录找到含 \\documentclass 的 .tex"
    if prefer_migrated:
        mig = [t for t in cands if "migrat" in t.name.lower()]
        if mig:
            return mig[0], "未指定 --migrated，按文件名取 %s" % mig[0]
        return None, ("未指定 --migrated 且无法按文件名推断迁移稿；"
                      "请显式传入 --migrated")
    return cands[0], "未指定 --original，取 %s" % cands[0]


# ------------------------------------------------------------ main -------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="迁移定稿：合规 + 编译 + diff + 装配")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--original", default=None)
    ap.add_argument("--migrated", default=None)
    ap.add_argument("--cls", default=None)
    ap.add_argument("--timeout", type=int, default=60,
                    help="单轮 pdflatex 超时秒数（有界）")
    ap.add_argument("--passes", type=int, default=2,
                    help="pdflatex 轮数上限（有界）")
    args = ap.parse_args(argv)

    work = Path(args.work)
    out_dir = Path(args.output)
    (work / "migration").mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    case, notes = load_case(args.input)
    uncertainty = list(notes)
    fields, dialect_note = normalize_contract(case.get("output_contract"))

    original, note = locate_tex(args.input, args.original, False)
    if note:
        uncertainty.append(note)
    migrated, note = locate_tex(args.input, args.migrated, True)
    if note:
        uncertainty.append(note)
    cls = args.cls
    if cls is None:
        cands = sorted(Path(args.input).rglob("*.cls"))
        if cands:
            cls = str(cands[0])
            uncertainty.append("未指定 --cls，取 %s" % cls)

    artifacts, blocking = [], []
    ctx = {}

    # ---- 迁移稿落盘 /app/output（可继续编辑的源码）----
    migrated_text = ""
    if migrated and Path(migrated).is_file():
        migrated_text = read_text(migrated)
        dest = out_dir / Path(migrated).name
        if Path(migrated).resolve() != dest.resolve():
            shutil.copy2(migrated, dest)
        ctx["migrated_out"] = dest.name
        artifacts.append(dest.name)
        if cls and Path(cls).is_file():
            cdest = out_dir / Path(cls).name
            if Path(cls).resolve() != cdest.resolve():
                shutil.copy2(cls, cdest)
            artifacts.append(cdest.name)
    else:
        blocking.append("迁移稿缺失，无法交付")

    # ---- 合规检查 ----
    compliance = {"required_fields": [], "sections": None, "compile": None,
                  "overall": "fail"}
    if migrated_text:
        required = class_required_fields(cls)
        compliance["required_fields"] = check_required(required,
                                                       migrated_text)
        for r in compliance["required_fields"]:
            if not r["ok"]:
                blocking.append("必填字段 \\%s：%s" % (r["field"],
                                                       r["status"]))
        if original and Path(original).is_file():
            sec = check_sections(read_text(original), migrated_text)
            compliance["sections"] = sec
            if not sec["ok"]:
                blocking.append("章节未映射：%s" % ", ".join(sec["missing"]))
        comp = compile_check(migrated, cls, work, args.timeout, args.passes)
        compliance["compile"] = comp
        if comp["status"] == "skipped":
            uncertainty.append(comp["reason"])
        elif not comp["ok"]:
            blocking.append("编译验证未通过：%s"
                            % ("；".join(comp["errors"]) or "未知错误"))
        ctx["compile_ok"] = comp["ok"]
        passed = (all(r["ok"] for r in compliance["required_fields"])
                  and (compliance["sections"] is None
                       or compliance["sections"]["ok"]))
        compliance["overall"] = "pass" if passed else "fail"
    if ctx.get("compile_ok") is None:
        ctx["compile_ok"] = None

    # ---- 最小 diff ----
    diff_rep = None
    if migrated_text and original and Path(original).is_file():
        diff_rep = intent_diff(read_text(original), migrated_text)
        write_intent_diff(diff_rep, out_dir / "intent_diff.md")
        ctx["diff_out"] = "intent_diff.md"
        artifacts.append("intent_diff.md")
        if diff_rep["text_changes"]:
            uncertainty.append(
                "正文存在 %d 处实际文字改动，见 intent_diff.md，"
                "需 Agent 确认意图保留" % diff_rep["text_changes"])
    else:
        uncertainty.append("缺少原稿或迁移稿，未生成 intent_diff")

    # ---- compliance 报告落盘 ----
    (out_dir / "compliance.json").write_text(
        json.dumps(compliance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    cl = ["# 迁移合规检查清单（compliance）", ""]
    cl.append("## 模板必填字段")
    cl.append("")
    cl.append("| 字段 | 状态 | 判定 | 当前值 |")
    cl.append("| --- | --- | --- | --- |")
    for r in compliance["required_fields"]:
        cl.append("| \\%s | %s | %s | %s |"
                  % (r["field"], r["status"],
                     "通过" if r["ok"] else "**不合规**",
                     r["value"] or "—"))
    if not compliance["required_fields"]:
        cl.append("| （模板未检出必填项，或无模板文件）| | | |")
    cl.append("")
    sec = compliance["sections"]
    if sec:
        cl.append("## 章节映射")
        cl.append("")
        cl.append("- 原稿章节数：%d；未落实：%s"
                  % (sec["original_count"],
                     ", ".join(sec["missing"]) or "无（全部落实）"))
        cl.append("")
    comp = compliance["compile"]
    if comp:
        cl.append("## 编译验证")
        cl.append("")
        cl.append("- 状态：%s；通过：%s；轮数：%d"
                  % (comp["status"],
                     {True: "是", False: "否", None: "未执行（降级）"}
                     [comp["ok"]], comp["passes"]))
        if comp.get("pdf_pages_note"):
            cl.append("- %s" % comp["pdf_pages_note"])
        if comp.get("reason"):
            cl.append("- 说明：%s" % comp["reason"])
        for e in comp.get("errors", []):
            cl.append("- 错误：`%s`" % e)
        cl.append("")
    cl.append("## 总结论：**%s**"
              % ("合规" if compliance["overall"] == "pass"
                 else "不合规（不放行，须修复后重跑 finalize.py）"))
    cl.append("")
    for b in blocking:
        cl.append("- 阻断项：%s" % b)
    if blocking:
        cl.append("")
    (out_dir / "compliance.md").write_text("\n".join(cl) + "\n",
                                           encoding="utf-8")
    ctx["compliance_out"] = "compliance.md"
    artifacts += ["compliance.json", "compliance.md"]
    plan = work / "migration" / "migration_plan.md"
    if plan.is_file():
        ctx["plan_out"] = str(plan)

    # ---- result.json ----
    for f in fields:
        if fill_field(f["name"], ctx) is None:
            uncertainty.append("契约字段 %s 无对应真实产物，按契约置 null"
                               % f["name"])
    if not migrated_text:
        status = "failed"
    elif blocking or ctx.get("compile_ok") is not True:
        status = "partial"
    else:
        status = "complete"
    result = {
        "case_id": case.get("case_id"),
        "status": status,
        "contract_dialect": dialect_note,
        "compliance_overall": compliance["overall"],
        "blocking_issues": blocking,
        "sources": [str(p) for p in (original, migrated, cls) if p],
        "uncertainty": uncertainty,
        "artifacts": sorted(set(artifacts)),
    }
    for f in fields:
        result[f["name"]] = fill_field(f["name"], ctx)
    if not fields and isinstance(case.get("output_contract"), str):
        result["contract_raw"] = case["output_contract"]
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print("[finalize] 合规总结论：%s" % compliance["overall"])
    for r in compliance["required_fields"]:
        print("[finalize]   必填 \\%s -> %s" % (r["field"], r["status"]))
    if compliance["compile"]:
        c = compliance["compile"]
        print("[finalize]   编译：status=%s ok=%s pages=%s"
              % (c["status"], c["ok"], c["pages"]))
    if diff_rep:
        print("[finalize]   正文文字改动：%d 处" % diff_rep["text_changes"])
    print("[finalize] result.json status=%s -> %s"
          % (status, out_dir / "result.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
