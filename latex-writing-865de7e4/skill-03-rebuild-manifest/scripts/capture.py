#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""capture.py — 把一次 LaTeX 构建固化为可复现 manifest（构建谱系取证）。

仅使用 Python3 标准库；pdflatex / bibtex / pdftotext 运行时探测，缺失时诚实降级。

做的事（确定性机械工作，不做写作决策）：
  1. 把工程整体复制到独立构建目录（镜像 \\include 子目录），不碰原始工程；
  2. 在构建目录内的主文件“副本”里注入 \\listfiles（临时副本注入，原文件零改动）；
  3. 有界多轮编译：pdflatex 至多 4 轮，bibtex 按需（aux 出现 \\citation 且有 .bib）；
     以“全部 .aux 文件拼接哈希相邻两轮不变”为收敛判据；
  4. 从 .log 的 \\listfiles 区块提取文档类与宏包逐版本清单、引擎与发行版版本、
     使用字体（.pfb/.ttf/.otf），并记录精确命令序列与轮次；
  5. 记录全部输入文件 SHA256、PDF 页数、pdftotext 全文文本哈希；
  6. 输出 manifest.json（机读）与 manifest.md（人读）。

用法：
  python3 capture.py --project /path/to/project --main main.tex \
      --outdir /app/work/manifest
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

MAX_PASSES = 4
COMPILE_TIMEOUT = 180  # 单轮编译超时（秒）

# 构建产物 / 缓存等不纳入输入哈希清单的扩展名与目录名
AUX_EXTS = {".aux", ".log", ".out", ".toc", ".lof", ".lot", ".bbl", ".blg",
            ".bcf", ".run.xml", ".synctex.gz", ".fls", ".fdb_latexmk", ".pdf",
            ".nav", ".snm", ".vrb", ".idx", ".ind", ".ilg", ".glo", ".gls"}
SKIP_DIRS = {".git", ".svn", "__pycache__"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def find_tool(name):
    """探测外部工具；返回 {"path":..., "version":...} 或 None。"""
    path = shutil.which(name)
    if not path:
        return None
    version = None
    try:
        if name == "pdftotext":
            p = subprocess.run([path, "-v"], capture_output=True, text=True, timeout=20)
            first = ((p.stderr or "") + (p.stdout or "")).strip().splitlines()
        else:
            p = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20)
            first = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
        version = first[0].strip() if first else "unknown"
    except Exception as exc:  # 探测失败也要如实记录
        version = "unknown (probe failed: %s)" % exc
    return {"path": path, "version": version}


def collect_inputs(project_dir):
    """收集工程内全部源输入文件（排除构建产物），相对路径 + SHA256。"""
    inputs = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1].lower()
            if ext in AUX_EXTS:
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, project_dir).replace(os.sep, "/")
            inputs.append({"path": rel, "sha256": sha256_file(full),
                           "bytes": os.path.getsize(full)})
    inputs.sort(key=lambda x: x["path"])
    return inputs


def mirror_project(project_dir, build_dir):
    """把工程整体复制到独立构建目录（保留子目录结构，镜像 \\include 需求）。"""
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_root = os.path.relpath(root, project_dir)
        for d in dirs:
            os.makedirs(os.path.join(build_dir, rel_root, d), exist_ok=True)
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in AUX_EXTS:
                continue  # 不带旧产物进构建目录，保证是“干净构建”
            src = os.path.join(root, fn)
            dst = os.path.join(build_dir, rel_root, fn)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


def inject_listfiles(build_dir, main_tex):
    """在构建目录内的主文件副本中注入 \\listfiles（绝不改原始工程）。

    返回是否注入成功。注入点：首个含 \\documentclass 的行之后。
    """
    path = os.path.join(build_dir, main_tex)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    # 仅当存在“行首（可缩进）的 \listfiles 命令”时才视为已开启；
    # 避免把 \verb|\listfiles| 或注释中的纯文本提及误判为已开启
    if re.search(r"(?m)^[ \t]*\\listfiles(?![a-zA-Z])", text):
        return True  # 工程本来就要求列版本，直接尊重
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if "\\documentclass" in line:
            lines.insert(i + 1, "\\listfiles % injected by capture.py on the build-dir copy only\n")
            with open(path, "w", encoding="utf-8") as f:
                f.write("".join(lines))
            return True
    return False


def aux_fingerprint(build_dir):
    """全部 .aux 内容按文件名排序拼接后的哈希；无 aux 时返回 None。"""
    auxes = []
    for root, _dirs, files in os.walk(build_dir):
        for fn in files:
            if fn.endswith(".aux"):
                auxes.append(os.path.join(root, fn))
    if not auxes:
        return None
    h = hashlib.sha256()
    for p in sorted(auxes):
        rel = os.path.relpath(p, build_dir).replace(os.sep, "/")
        h.update(rel.encode("utf-8"))
        with open(p, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def aux_has_citation(build_dir):
    for root, _dirs, files in os.walk(build_dir):
        for fn in files:
            if fn.endswith(".aux"):
                try:
                    with open(os.path.join(root, fn), "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except OSError:
                    continue
                if "\\citation{" in content and "\\bibdata{" in content:
                    return True
    return False


def run_step(argv, cwd):
    """执行一步编译命令，返回 {exit_code, elapsed_s, timed_out}。"""
    t0 = time.time()
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=COMPILE_TIMEOUT)
        return {"exit_code": p.returncode,
                "elapsed_s": round(time.time() - t0, 2),
                "timed_out": False,
                "stdout_tail": (p.stdout or b"").decode("utf-8", "replace")[-2000:],
                "stderr_tail": (p.stderr or b"").decode("utf-8", "replace")[-2000:]}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "elapsed_s": COMPILE_TIMEOUT, "timed_out": True,
                "stdout_tail": "", "stderr_tail": "timeout after %ds" % COMPILE_TIMEOUT}


FILE_ENTRY_RE = re.compile(r"^[A-Za-z0-9_./\-+]+\.[A-Za-z]{1,8}$")
DATE_RE = re.compile(r"^\d{4}[/\-]\d{2}[/\-]\d{2}")


def parse_file_list(log_text):
    """解析 \\listfiles 在 .log 中输出的 *File List* 区块。

    逐条返回 {"file", "version", "date", "description"}；只接受首 token 形似
    文件名（含扩展名）的行，以避开 pdflatex 日志 79 列折行产生的续行噪音。
    """
    entries = []
    in_block = False
    for line in log_text.splitlines():
        s = line.strip()
        if "*File List*" in s:
            in_block = True
            continue
        if not in_block:
            continue
        if s and set(s) == {"*"}:  # 收尾的一行星号
            break
        if not s:
            continue
        parts = s.split(None, 2)
        fname = parts[0]
        if not FILE_ENTRY_RE.match(fname):
            continue
        date = version = None
        desc = ""
        rest = s[len(fname):].strip()
        if rest:
            m = DATE_RE.match(rest)
            if m:
                date = m.group(0)
                rest = rest[m.end():].strip()
            if rest.startswith("v") and len(rest) > 1 and (rest[1].isdigit() or rest[1] == " "):
                vparts = rest.split(None, 1)
                version = vparts[0]
                desc = vparts[1] if len(vparts) > 1 else ""
            else:
                desc = rest
        entries.append({"file": os.path.basename(fname),
                        "date": date, "version": version,
                        "description": desc.strip()})
    return entries


def parse_engine(log_text):
    """从日志首行解析引擎与发行版，例如 'This is pdfTeX, Version ... (TeX Live 2026)'。"""
    first = log_text.splitlines()[0] if log_text.splitlines() else ""
    m = re.search(r"This is ([A-Za-z]+), Version ([\d.\-]+)\s*\(([^)]+)\)", first)
    if m:
        return {"line": first.strip(), "name": m.group(1),
                "version": m.group(2), "distribution": m.group(3)}
    return {"line": first.strip(), "name": None, "version": None, "distribution": None}


def parse_fonts(log_text):
    """从日志中提取实际嵌入/使用的字体文件（.pfb/.ttf/.otf 基名，去重排序）。"""
    fonts = set()
    # 组内不允许出现 < 或 >，保证从离字体扩展名最近的 "<" 开始；
    # pdflatex 日志按 ~79 列折行，路径中可能插入换行，先去除全部空白再取基名。
    for m in re.finditer(r"<([^<>]{1,300}?\.(?:pfb|ttf|otf))>", log_text, re.S):
        cleaned = re.sub(r"\s+", "", m.group(1))
        fonts.add(cleaned.split("/")[-1])
    return sorted(fonts)


def parse_pages(log_text):
    m = re.search(r"Output written on [^\s(]+ \((\d+) pages?", log_text)
    return int(m.group(1)) if m else None


def pdftotext_hash(pdf_path, tool):
    """返回 (sha256, char_count, note)。工具缺失或失败时返回 (None, None, 原因)。"""
    if not tool:
        return None, None, "pdftotext 不可用，无法计算全文文本哈希"
    try:
        p = subprocess.run([tool["path"], "-enc", "UTF-8", pdf_path, "-"],
                           capture_output=True, timeout=60)
    except Exception as exc:
        return None, None, "pdftotext 调用失败: %s" % exc
    if p.returncode != 0:
        return None, None, "pdftotext 退出码 %s" % p.returncode
    data = p.stdout
    return sha256_bytes(data), len(data.decode("utf-8", "replace")), None


def write_manifest_md(manifest, path):
    m = manifest
    lines = []
    lines.append("# LaTeX 构建谱系 manifest（人读版）")
    lines.append("")
    lines.append("> 本文件由 capture.py 自动生成，与 manifest.json 内容一致，供人工核对。")
    lines.append("")
    lines.append("- 生成时间（UTC）：%s" % m["created_utc"])
    lines.append("- 工程主文件：%s" % m["project"]["main_tex"])
    lines.append("- 状态：%s" % m["status"])
    if m.get("limitations"):
        lines.append("- 限制/降级说明：")
        for lim in m["limitations"]:
            lines.append("  - %s" % lim)
    lines.append("")
    lines.append("## 工具与引擎")
    lines.append("")
    for tool in ("pdflatex", "bibtex", "pdftotext"):
        t = m["tools"].get(tool)
        if t:
            lines.append("- %s：`%s`（%s）" % (tool, t["path"], t["version"]))
        else:
            lines.append("- %s：**不可用（已降级）**" % tool)
    eng = m.get("engine") or {}
    lines.append("- 引擎日志首行：`%s`" % (eng.get("line") or "（无日志）"))
    lines.append("")
    lines.append("## 构建过程")
    lines.append("")
    b = m["build"]
    lines.append("- 独立构建目录：是；\\listfiles 仅注入构建目录内副本：%s"
                 % ("是" if b["listfiles_injected_on_copy"] else "否"))
    lines.append("- 编译轮次（pdflatex）：%d；bibtex 运行：%s"
                 % (b["passes"], "是" if b["bibtex_ran"] else "否"))
    lines.append("- aux 收敛：%s（判据：相邻两轮全部 .aux 拼接哈希不变）"
                 % ("是" if b["aux_converged"] else "否"))
    lines.append("- 编译成功：%s；PDF 页数：%s；PDF 字节 SHA256：`%s`"
                 % ("是" if b["compile_ok"] else "否",
                    b["pdf_pages"], b.get("pdf_sha256") or "—"))
    lines.append("- 全文文本（pdftotext, UTF-8）SHA256：`%s`"
                 % (m["output_text"].get("sha256") or "—（不可用）"))
    lines.append("")
    lines.append("### 精确命令序列")
    lines.append("")
    lines.append("| # | 命令 | 退出码 | 耗时(s) |")
    lines.append("|---|------|--------|---------|")
    for st in b["steps"]:
        lines.append("| %d | `%s` | %s | %s |"
                     % (st["seq"], " ".join(st["argv"]),
                        st.get("exit_code"), st.get("elapsed_s")))
    lines.append("")
    lines.append("## 文档类与宏包逐版本清单（\\listfiles，共 %d 条）"
                 % len(m["file_versions"]))
    lines.append("")
    lines.append("| 文件 | 日期 | 版本 | 说明 |")
    lines.append("|------|------|------|------|")
    for e in m["file_versions"]:
        lines.append("| %s | %s | %s | %s |"
                     % (e["file"], e.get("date") or "—", e.get("version") or "—",
                        (e.get("description") or "").replace("|", "\\|")[:80]))
    lines.append("")
    lines.append("## 使用字体（日志中提取，共 %d 个）" % len(m["fonts"]))
    lines.append("")
    for f in m["fonts"]:
        lines.append("- %s" % f)
    lines.append("")
    lines.append("## 输入文件 SHA256（共 %d 个）" % len(m["inputs"]))
    lines.append("")
    lines.append("| 文件 | 字节 | SHA256 |")
    lines.append("|------|------|--------|")
    for e in m["inputs"]:
        lines.append("| %s | %d | `%s` |" % (e["path"], e["bytes"], e["sha256"]))
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="固化 LaTeX 构建为可复现 manifest")
    ap.add_argument("--project", required=True, help="LaTeX 工程目录（原始输入，绝不修改）")
    ap.add_argument("--main", default=None, help="主 .tex（相对工程目录）；缺省自动探测含 \\documentclass 的文件")
    ap.add_argument("--outdir", default="/app/work/manifest", help="manifest 输出目录")
    ap.add_argument("--work-root", default=None,
                    help="构建目录根（缺省 <outdir 的父目录>/build）")
    args = ap.parse_args()

    project_dir = os.path.abspath(args.project)
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    build_dir = os.path.join(os.path.abspath(args.work_root), "build") if args.work_root \
        else os.path.join(os.path.dirname(outdir), "build")

    limitations = []
    manifest = {
        "manifest_version": "1.0",
        "kind": "latex-build-manifest",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": "capture.py (latex-rebuild-manifest skill)",
        "project": {"root_name": os.path.basename(project_dir), "main_tex": args.main},
        "tools": {},
        "engine": None,
        "inputs": [],
        "build": {"build_dir_isolated": True, "listfiles_injected_on_copy": False,
                  "steps": [], "passes": 0, "bibtex_ran": False,
                  "aux_converged": None, "aux_fingerprint": None,
                  "compile_ok": False, "pdf_pages": None,
                  "pdf_bytes": None, "pdf_sha256": None},
        "file_versions": [],
        "fonts": [],
        "output_text": {"sha256": None, "chars": None, "note": None},
        "status": "failed",
        "limitations": limitations,
    }

    if not os.path.isdir(project_dir):
        limitations.append("工程目录不存在：%s" % project_dir)
        manifest["status"] = "blocked"
        _emit(manifest, outdir)
        return 2

    # 主文件探测
    main_tex = args.main
    if not main_tex:
        candidates = []
        for root, _dirs, files in os.walk(project_dir):
            for fn in files:
                if fn.endswith(".tex"):
                    full = os.path.join(root, fn)
                    try:
                        with open(full, "r", encoding="utf-8", errors="replace") as f:
                            if "\\documentclass" in f.read():
                                candidates.append(os.path.relpath(full, project_dir))
                    except OSError:
                        pass
        if not candidates:
            limitations.append("未找到含 \\documentclass 的主 .tex 文件")
            manifest["status"] = "blocked"
            _emit(manifest, outdir)
            return 2
        main_tex = sorted(candidates)[0]
        if len(candidates) > 1:
            limitations.append("存在多个含 \\documentclass 的文件，已选 %s；"
                               "如不对请用 --main 指定" % main_tex)
    manifest["project"]["main_tex"] = main_tex
    if not os.path.isfile(os.path.join(project_dir, main_tex)):
        limitations.append("主文件不存在：%s" % main_tex)
        manifest["status"] = "blocked"
        _emit(manifest, outdir)
        return 2

    # 输入哈希（对原始工程计算，先于任何复制/注入）
    manifest["inputs"] = collect_inputs(project_dir)

    # 工具探测
    pdflatex = find_tool("pdflatex")
    bibtex = find_tool("bibtex")
    pdftotext = find_tool("pdftotext")
    manifest["tools"] = {"pdflatex": pdflatex, "bibtex": bibtex, "pdftotext": pdftotext}
    if not pdflatex:
        limitations.append("pdflatex 不可用：只记录输入哈希，无法编译与提取版本清单")
        manifest["status"] = "partial"
        _emit(manifest, outdir)
        return 0
    if not pdftotext:
        limitations.append("pdftotext 不可用：全文文本哈希将缺失，重建比对会降级为 inconclusive")

    # 镜像工程到独立构建目录 + 副本注入 \listfiles
    mirror_project(project_dir, build_dir)
    manifest["build"]["listfiles_injected_on_copy"] = inject_listfiles(build_dir, main_tex)
    if not manifest["build"]["listfiles_injected_on_copy"]:
        limitations.append("未能在主文件副本中注入 \\listfiles（未找到 \\documentclass 行），"
                           "版本清单可能为空")

    jobname = os.path.splitext(os.path.basename(main_tex))[0]
    steps = manifest["build"]["steps"]
    seq = 0
    prev_fp = None
    converged = False
    bibtex_done = False
    pdf_path = os.path.join(build_dir, jobname + ".pdf")

    for rnd in range(1, MAX_PASSES + 1):
        seq += 1
        argv = [pdflatex["path"], "-interaction=nonstopmode", main_tex]
        res = run_step(argv, build_dir)
        steps.append({"seq": seq, "tool": "pdflatex", "argv": argv[1:],
                      "pass": rnd, **{k: res[k] for k in ("exit_code", "elapsed_s", "timed_out")}})
        manifest["build"]["passes"] = rnd
        if res["timed_out"]:
            limitations.append("pdflatex 第 %d 轮超时（%ds），提前终止" % (rnd, COMPILE_TIMEOUT))
            break

        # bibtex 按需：出现引用且尚未运行过
        if (not bibtex_done) and bibtex and aux_has_citation(build_dir):
            bib_candidates = [e["path"] for e in manifest["inputs"] if e["path"].endswith(".bib")]
            if bib_candidates:
                seq += 1
                argv = [bibtex["path"], jobname]
                res = run_step(argv, build_dir)
                steps.append({"seq": seq, "tool": "bibtex", "argv": argv[1:],
                              "pass": None,
                              **{k: res[k] for k in ("exit_code", "elapsed_s", "timed_out")}})
                bibtex_done = True
                manifest["build"]["bibtex_ran"] = True
                if res["exit_code"] not in (0, 1):  # bibtex 警告返回 1 属常见
                    limitations.append("bibtex 退出码 %s，请人工核对 .blg" % res["exit_code"])
        elif (not bibtex_done) and not bibtex and aux_has_citation(build_dir):
            limitations.append("检测到 \\citation 但 bibtex 不可用，文献引用可能未解析")
            bibtex_done = True  # 不再重复提示

        fp = aux_fingerprint(build_dir)
        manifest["build"]["aux_fingerprint"] = fp
        if fp is not None and fp == prev_fp:
            converged = True
            break
        prev_fp = fp

    manifest["build"]["aux_converged"] = converged
    if not converged:
        limitations.append("%d 轮内 aux 未收敛（可能有不稳定交叉引用），"
                           "manifest 仍已记录实际轮次" % MAX_PASSES)

    # 编译结果
    log_path = os.path.join(build_dir, jobname + ".log")
    log_text = ""
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            log_text = f.read()
    manifest["engine"] = parse_engine(log_text)
    manifest["file_versions"] = parse_file_list(log_text)
    manifest["fonts"] = parse_fonts(log_text)
    manifest["build"]["pdf_pages"] = parse_pages(log_text)

    if os.path.isfile(pdf_path):
        manifest["build"]["compile_ok"] = True
        manifest["build"]["pdf_bytes"] = os.path.getsize(pdf_path)
        manifest["build"]["pdf_sha256"] = sha256_file(pdf_path)
        th, tc, note = pdftotext_hash(pdf_path, pdftotext)
        manifest["output_text"] = {"sha256": th, "chars": tc, "note": note}
        if note:
            limitations.append(note)
    else:
        limitations.append("未生成 PDF（编译失败），请检查构建目录中的 .log：%s" % log_path)

    if not manifest["file_versions"]:
        limitations.append("\\listfiles 版本清单为空（日志中无 *File List* 区块）")

    if manifest["build"]["compile_ok"]:
        manifest["status"] = "complete" if not limitations else "partial"
    else:
        manifest["status"] = "partial"

    _emit(manifest, outdir)
    return 0


def _emit(manifest, outdir):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    write_manifest_md(manifest, os.path.join(outdir, "manifest.md"))
    print("[capture] status=%s passes=%s file_versions=%d -> %s"
          % (manifest["status"], manifest["build"]["passes"],
             len(manifest["file_versions"]), outdir))


if __name__ == "__main__":
    sys.exit(main())
