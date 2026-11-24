#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citebuild.py — LaTeX 多轮收敛编译验证（仅标准库 + 运行时探测外部工具）。

流程：latex → bibtex/biber → latex → latex …（有界，默认至多 6 轮），
在独立构建目录中镜像工程（含 \\include 子目录），逐轮从 .log/.blg 提取
undefined citation / undefined reference / multiply-defined label 警告集合，
收敛判据：相邻两轮 latex 的警告集合相同且 bib 步骤已执行（若有参考文献）。

输出：
  rounds.json         —— 每轮工具、返回码、警告集合、收敛标志、每个引用键的
                         最终状态（resolved / unresolved + 原因：缺条目/缺字段/
                         bibtex 报错）、警告轮次曲线
  citebuild_report.md —— 人读摘要

红线：未解析引用绝不静默忽略——全部写入 rounds.json 并以非零退出码暴露。
降级：pdflatex/bibtex/biber 缺失时诚实标注"编译验证不可用"，退出码 3，
      静态审计（citeaudit.py）不受影响。

用法：
  python3 citebuild.py --project <工程目录> [--main main.tex]
      --build-dir <独立构建目录> --work <输出目录>
      [--engine pdflatex] [--max-rounds 6] [--banner "标注"]
退出码：0 收敛且无未解析引用；2 已收敛但仍有未解析引用/交叉引用；
        3 编译工具缺失（诚实降级）；1 参数/运行错误。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

AUX_EXT = {".aux", ".log", ".pdf", ".bbl", ".blg", ".out", ".toc", ".lof",
           ".lot", ".fls", ".fdb_latexmk", ".synctex.gz", ".run.xml", ".bcf",
           ".nav", ".snm", ".vrb"}
SKIP_DIRS = {".git", "_citebuild", "__pycache__"}

RE_CITE_UNDEF = re.compile(r"(?:LaTeX|Package \w+)\s+Warning:\s+Citation `([^']+)'"
                           r"(?:.*?)undefined", re.I)
RE_REF_UNDEF = re.compile(r"LaTeX Warning: Reference `([^']+)'"
                          r"(?:.*?)undefined", re.I)
RE_MULTILABEL = re.compile(r"(?:LaTeX Warning: )?Label `([^']+)'"
                           r" multiply defined", re.I)
RE_BLG_BIBTEX_WARN = re.compile(r"^Warning--(.+)$", re.M)
RE_BLG_BIBTEX_ERR = re.compile(r"^(I (?:couldn't|was|found|didn't).*|"
                               r"Repeated entry.*)$", re.M)
RE_BIBER_WARN = re.compile(r"^(?:WARN|ERROR) - (.*)$", re.M)
RE_EMPTY_FIELD = re.compile(r"empty (\w+) in (.+)$", re.I)
RE_NO_ENTRY = re.compile(r"didn't find a database entry for [`\"]?(.+?)[`\"]?$",
                         re.I)


def probe(tool):
    return shutil.which(tool) is not None


def find_main(project, main=None):
    if main:
        return main
    for dirpath, dirnames, filenames in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in sorted(filenames):
            if f.endswith(".tex"):
                p = os.path.join(dirpath, f)
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        if "\\documentclass" in fh.read():
                            return os.path.relpath(p, project)
                except OSError:
                    pass
    return None


def detect_bib_tool(project):
    """biblatex → biber；\\bibliography/.bib → bibtex；否则 None。"""
    has_bib_resource = False
    for dirpath, dirnames, filenames in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith(".tex"):
                try:
                    with open(os.path.join(dirpath, f), encoding="utf-8",
                              errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                if "biblatex" in text or "\\addbibresource" in text:
                    return "biber"
                if "\\bibliography" in text:
                    has_bib_resource = True
            elif f.endswith(".bib"):
                has_bib_resource = True
    return "bibtex" if has_bib_resource else None


def mirror_project(project, build_dir):
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)
    for dirpath, dirnames, filenames in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                       and os.path.abspath(os.path.join(dirpath, d))
                       != os.path.abspath(build_dir)]
        rel = os.path.relpath(dirpath, project)
        target_dir = os.path.join(build_dir, rel) if rel != "." else build_dir
        os.makedirs(target_dir, exist_ok=True)
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in AUX_EXT:
                continue
            shutil.copy2(os.path.join(dirpath, f),
                         os.path.join(target_dir, f))


def run_cmd(cmd, cwd, timeout=180):
    env = dict(os.environ)
    env["max_print_line"] = "10000"  # kpathsea 环境变量，便于解析长行
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.returncode, proc.stdout.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return 124, "[citebuild] 命令超时（%ds）：%s" % (timeout, " ".join(cmd))
    except OSError as exc:
        return 127, "[citebuild] 命令无法执行：%s" % exc


def parse_log(log_text):
    return {
        "undefined_citations": sorted(set(RE_CITE_UNDEF.findall(log_text))),
        "undefined_references": sorted(set(RE_REF_UNDEF.findall(log_text))),
        "multiply_defined_labels": sorted(set(RE_MULTILABEL.findall(log_text))),
    }


def parse_blg(blg_text, tool):
    warnings, errors = [], []
    if tool == "biber":
        for line in RE_BIBER_WARN.findall(blg_text):
            line = line.strip()
            if not line:
                continue
            if "didn't find a database entry" in line or "skip" in line.lower():
                warnings.append(line)
            else:
                (errors if blg_text.startswith("ERROR") else warnings).append(line)
    else:
        for w in RE_BLG_BIBTEX_WARN.findall(blg_text):
            warnings.append(w.strip())
        for e in RE_BLG_BIBTEX_ERR.findall(blg_text):
            e = e.strip()
            if "didn't find a database entry" in e:
                warnings.append(e)
            else:
                errors.append(e)
    return sorted(set(warnings)), sorted(set(errors))


def read_aux_citations(build_dir):
    """从全部 .aux 收集 \\citation{...}（含 \\include 子文件的 .aux）。"""
    keys = set()
    cre = re.compile(r"\\citation\{([^}]*)\}")
    for dirpath, _dirnames, filenames in os.walk(build_dir):
        for f in filenames:
            if f.endswith(".aux"):
                try:
                    with open(os.path.join(dirpath, f), encoding="utf-8",
                              errors="replace") as fh:
                        for m in cre.finditer(fh.read()):
                            keys.update(k.strip() for k in m.group(1).split(",")
                                        if k.strip())
                except OSError:
                    pass
    return sorted(keys)


def read_bib_keys(build_dir):
    keys = set()
    are = re.compile(r"@\w+\s*[({]\s*([^,\s]+)")
    for dirpath, _dirnames, filenames in os.walk(build_dir):
        for f in filenames:
            if f.endswith(".bib"):
                try:
                    with open(os.path.join(dirpath, f), encoding="utf-8",
                              errors="replace") as fh:
                        keys.update(m.group(1).strip()
                                    for m in are.finditer(fh.read()))
                except OSError:
                    pass
    return keys


def classify_unresolved(key, blg_warnings, blg_errors, bib_keys):
    """给出 unresolved 原因：缺条目 / 缺字段 / bibtex 报错。"""
    for w in blg_warnings:
        m = RE_EMPTY_FIELD.search(w)
        if m and m.group(2).strip().strip('"') == key:
            return "缺字段（bib 工具报告 empty %s）" % m.group(1)
        m = RE_NO_ENTRY.search(w)
        if m and m.group(1).strip() == key:
            return "缺条目（bib 数据库中不存在该键）"
    for e in blg_errors:
        if key in e:
            return "bibtex/biber 报错：%s" % e
    if key not in bib_keys:
        return "缺条目（bib 数据库中不存在该键）"
    return "条目存在但未通过编译解析（可能 bib 工具报错或样式异常，需人工核查）"


def render_report(data, banner=None):
    L = []
    if banner:
        L += [banner, ""]
    L.append("# 多轮收敛编译报告（citebuild）")
    L.append("")
    L.append(f"- 引擎：`{data.get('engine')}`；bib 工具：`{data.get('bib_tool')}`")
    L.append(f"- 构建目录：`{data.get('build_dir')}`")
    L.append(f"- 收敛：{'是' if data.get('converged') else '否'}"
             f"（判据：相邻两轮 latex 警告集合相同）")
    if data.get("status_note"):
        L.append(f"- 状态说明：{data['status_note']}")
    L.append("")
    curve = data.get("curve", [])
    if curve:
        L.append("## 警告轮次曲线")
        L.append("")
        L.append("| latex 轮次 | 未定义引用 | 未定义交叉引用 | 重复标签 |")
        L.append("| --- | --- | --- | --- |")
        for c in curve:
            L.append(f"| {c['round']} | {c['undefined_citations']} "
                     f"| {c['undefined_references']} "
                     f"| {c['multiply_defined_labels']} |")
        L.append("")
    final = data.get("final", {})
    L.append("## 每个引用键的最终状态")
    L.append("")
    L.append("| 键 | 状态 |")
    L.append("| --- | --- |")
    for key, st in sorted(final.get("key_status", {}).items()):
        L.append(f"| `{key}` | {st} |")
    if not final.get("key_status"):
        L.append("| — | 未执行编译或工程无引用 |")
    L.append("")
    un = final.get("unresolved_citations", {})
    if un:
        L.append("**未解析引用（绝不静默忽略，需人工处置）：**")
        L.append("")
        for k, reason in sorted(un.items()):
            L.append(f"- `{k}`：{reason}")
        L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="LaTeX 多轮收敛编译验证")
    ap.add_argument("--project", required=True)
    ap.add_argument("--main", default=None, help="主 .tex（相对工程目录）")
    ap.add_argument("--build-dir", required=True, help="独立构建目录（会被重建）")
    ap.add_argument("--work", required=True, help="输出目录")
    ap.add_argument("--engine", default="pdflatex")
    ap.add_argument("--max-rounds", type=int, default=6)
    ap.add_argument("--banner", default=None)
    args = ap.parse_args(argv)

    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print(f"[citebuild] 错误：工程目录不存在：{project}", file=sys.stderr)
        return 1
    os.makedirs(args.work, exist_ok=True)
    rounds_path = os.path.join(args.work, "rounds.json")
    report_path = os.path.join(args.work, "citebuild_report.md")

    main_rel = find_main(project, args.main)
    bib_tool = detect_bib_tool(project)

    # ---- 工具探测：缺失则诚实降级 ----
    missing = [t for t in [args.engine, bib_tool] if t and not probe(t)]
    if main_rel is None:
        missing.append("main.tex（未找到含 \\documentclass 的文件）")
    if missing:
        data = {
            "generated_by": "citebuild.py",
            "banner": args.banner,
            "status": "compile_unavailable",
            "status_note": "编译验证不可用：" + "；".join(
                f"缺少 {m}" for m in missing)
            + "。静态审计（citeaudit.py）结果仍然有效。",
            "engine": args.engine, "bib_tool": bib_tool,
            "build_dir": os.path.abspath(args.build_dir),
            "converged": False, "rounds": [], "curve": [],
            "final": {"key_status": {}, "unresolved_citations": {}},
        }
        with open(rounds_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(render_report(data, banner=args.banner))
        print(f"[citebuild] 降级：{data['status_note']}")
        return 3

    mirror_project(project, args.build_dir)
    build_dir = os.path.abspath(args.build_dir)
    job = os.path.splitext(os.path.basename(main_rel))[0]
    main_dir = os.path.dirname(os.path.join(build_dir, main_rel)) or build_dir

    rounds, curve = [], []
    prev_sets = None
    converged = False
    bib_ran = False
    plan = [args.engine]
    if bib_tool:
        plan.append(bib_tool)
    plan.extend([args.engine] * (args.max_rounds - len(plan)))

    for idx, tool in enumerate(plan[:args.max_rounds], 1):
        if tool == bib_tool:
            cmd, rc, out = [bib_tool, job], None, None
            rc, out = run_cmd(cmd, main_dir)
            blg = os.path.join(main_dir, job + ".blg")
            blg_text = ""
            if os.path.isfile(blg):
                with open(blg, encoding="utf-8", errors="replace") as fh:
                    blg_text = fh.read()
            warns, errs = parse_blg(blg_text, bib_tool)
            rounds.append({"round": idx, "tool": tool, "returncode": rc,
                           "blg_warnings": warns, "blg_errors": errs})
            bib_ran = True
        else:
            rc, out = run_cmd([args.engine, "-interaction=nonstopmode",
                               "-recorder", main_rel], build_dir)
            log = os.path.join(build_dir, job + ".log")
            log_text = ""
            if os.path.isfile(log):
                with open(log, encoding="utf-8", errors="replace") as fh:
                    log_text = fh.read()
            sets = parse_log(log_text)
            rounds.append({"round": idx, "tool": tool, "returncode": rc, **sets})
            curve.append({"round": idx,
                          "undefined_citations": len(sets["undefined_citations"]),
                          "undefined_references": len(sets["undefined_references"]),
                          "multiply_defined_labels":
                              len(sets["multiply_defined_labels"])})
            if prev_sets is not None and sets == prev_sets and (bib_ran or not bib_tool):
                converged = True
                break
            prev_sets = sets

    # ---- 汇总最终状态 ----
    last_engine = next((r for r in reversed(rounds) if r["tool"] == args.engine), {})
    undef_cites = set(last_engine.get("undefined_citations", []))
    undef_refs = set(last_engine.get("undefined_references", []))
    multi_labels = set(last_engine.get("multiply_defined_labels", []))
    blg_warns, blg_errs = [], []
    for r in rounds:
        blg_warns += r.get("blg_warnings", [])
        blg_errs += r.get("blg_errors", [])
    cited = read_aux_citations(build_dir)
    bib_keys = read_bib_keys(build_dir)
    key_status, unresolved = {}, {}
    for key in cited:
        if key in undef_cites:
            reason = classify_unresolved(key, blg_warns, blg_errs, bib_keys)
            key_status[key] = "unresolved（%s）" % reason
            unresolved[key] = reason
        else:
            key_status[key] = "resolved"

    data = {
        "generated_by": "citebuild.py",
        "banner": args.banner,
        "status": "ok",
        "status_note": "" if converged else "达到轮次上限，警告集合仍在变化，未收敛",
        "engine": args.engine, "bib_tool": bib_tool,
        "build_dir": build_dir, "converged": converged,
        "rounds": rounds, "curve": curve,
        "final": {
            "key_status": key_status,
            "unresolved_citations": unresolved,
            "unresolved_references": sorted(undef_refs),
            "multiply_defined_labels": sorted(multi_labels),
        },
    }
    with open(rounds_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(render_report(data, banner=args.banner))

    n_un = len(unresolved) + len(undef_refs)
    print(f"[citebuild] 轮数 {len(rounds)}，收敛={converged}，"
          f"未解析引用 {len(unresolved)}，未解析交叉引用 {len(undef_refs)}，"
          f"重复标签 {len(multi_labels)}")
    print(f"[citebuild] 输出：{rounds_path}")
    return 2 if n_un else 0


if __name__ == "__main__":
    sys.exit(main())
