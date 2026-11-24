#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
texbuild.py — LaTeX 工程探测与有界多轮编译（仅 Python3 标准库）。

职责（确定性机械工作，不做任何源码修改决策）：
  1. 工程探测：主文件（含 \\documentclass 的 .tex）；引擎判定（出现 ctex/xeCJK/
     fontspec/unicode-math -> xelatex，否则 pdflatex）；文献工具（biblatex 或
     \\addbibresource -> biber；存在 .bib 或 \\bibliography -> bibtex）。
  2. 有界多轮编译：默认最多 4 轮引擎 + 文献工具按需，全部在独立构建目录中
     进行（-output-directory）。构建前预先镜像 \\include/\\input 目标的相对
     子目录——TeX 不会自动创建子目录里的 .aux，缺镜像会直接报
     "I can't write on file `chapters/methods.aux'"。
  3. 收敛判据：连续两轮全部 .aux 内容哈希一致，且最新日志无 "Rerun" 类提示。
  4. 诚实性：构建前删除目标 PDF；构建后校验 PDF 存在且 mtime 不早于本次构建
     开始时刻，绝不用旧 PDF 冒充成功。
  5. pdflatex/xelatex/bibtex/biber 运行时探测；缺失时输出诚实 blocked 报告，
     写清缺什么、需要什么。

用法：
  python3 texbuild.py --project <工程目录> --builddir <构建目录> \
      [--report <报告.json>] [--engine pdflatex|xelatex] [--max-rounds 4]

退出码：0=编译产出新鲜 PDF；1=存在 LaTeX 错误；3=blocked（缺外部工具）；
        4=找不到主文件；2=用法错误。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

ENGINE_CJK_HINT = re.compile(r"ctex|xeCJK|fontspec|unicode-math")
RE_DOCCLASS = re.compile(r"\\documentclass")
RE_INCLUDE = re.compile(r"\\(?:include|input)\s*\{([^}]+)\}")
RE_BIBLATEX = re.compile(r"biblatex|\\addbibresource")
RE_BIBLIOGRAPHY = re.compile(r"\\bibliography\s*\{")
RE_RERUN = re.compile(r"Rerun to get|Rerun LaTeX|Label\(s\) may have changed|"
                      r"There were undefined references|Citation .* undefined")

MAX_PRINT_LINE = 79  # TeX 日志默认 79 列包裹


def log_msg(msg):
    sys.stderr.write("[texbuild] %s\n" % msg)


def unwrap_lines(text):
    """把被 79 列包裹的日志行拼回逻辑行（供错误粗计数用）。"""
    out, buf = [], ""
    for ln in text.split("\n"):
        buf += ln
        if len(ln) >= MAX_PRINT_LINE:
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def find_main_file(project):
    """在工程中找含 \\documentclass 的 .tex，优先浅层、短路径。"""
    cands = []
    for root, _dirs, files in os.walk(project):
        for fn in files:
            if not fn.endswith(".tex"):
                continue
            p = os.path.join(root, fn)
            if RE_DOCCLASS.search(read_text(p)):
                rel = os.path.relpath(p, project)
                cands.append(rel)
    if not cands:
        return None
    cands.sort(key=lambda r: (r.count(os.sep), len(r)))
    return cands[0]


def all_tex_texts(project):
    texts = []
    for root, _dirs, files in os.walk(project):
        for fn in files:
            if fn.endswith(".tex"):
                texts.append(read_text(os.path.join(root, fn)))
    return texts


def detect_engine(project):
    blob = "\n".join(all_tex_texts(project))
    return "xelatex" if ENGINE_CJK_HINT.search(blob) else "pdflatex"


def detect_bib_tool(project):
    texts = all_tex_texts(project)
    blob = "\n".join(texts)
    has_bib_file = False
    for root, _dirs, files in os.walk(project):
        if any(fn.endswith(".bib") for fn in files):
            has_bib_file = True
            break
    if RE_BIBLATEX.search(blob):
        return "biber" if has_bib_file else None
    if has_bib_file or RE_BIBLIOGRAPHY.search(blob):
        return "bibtex"
    return None


RE_USEPACKAGE = re.compile(
    r"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\s*\{([^}]+)\}")
RE_DOCCLASS_ARG = re.compile(
    r"\\documentclass(?:\[[^\]]*\])?\s*\{([^}]+)\}")


def preflight_missing_packages(project):
    """编译前用 kpsewhich 机械核对 \\usepackage/\\RequirePackage/\\documentclass
    引用的 .sty/.cls 是否可解析（只报告，不修改）。缺 .sty 时 TeX 在
    nonstopmode 下会 Emergency stop，预检能让该根因即使日志被截断也可定位。"""
    wanted = []  # (文件名, 引用处)
    for text in all_tex_texts(project):
        for m in RE_USEPACKAGE.finditer(text):
            for name in m.group(1).split(","):
                name = name.strip()
                if name:
                    wanted.append((name if name.endswith(".sty")
                                   else name + ".sty", "\\usepackage"))
        for m in RE_DOCCLASS_ARG.finditer(text):
            name = m.group(1).strip()
            if name:
                wanted.append((name if name.endswith(".cls")
                               else name + ".cls", "\\documentclass"))
    missing = []
    if shutil.which("kpsewhich") is None:
        return missing, "无 kpsewhich，预检跳过"
    seen = set()
    for fname, via in wanted:
        if fname in seen:
            continue
        seen.add(fname)
        try:
            proc = subprocess.run(["kpsewhich", fname], timeout=20,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL)
            if not proc.stdout.decode("utf-8", "replace").strip():
                missing.append({"file": fname, "via": via})
        except (OSError, subprocess.TimeoutExpired):
            return missing, "kpsewhich 执行失败，预检不完整"
    return missing, None


def mirror_include_dirs(project, builddir):
    """预先在构建目录创建 \\include/\\input 目标的相对子目录（真实踩过的 bug：
    否则 TeX 无法写 chapters/xxx.aux，报 I can't write on file）。"""
    made = []
    for text in all_tex_texts(project):
        for m in RE_INCLUDE.finditer(text):
            rel = m.group(1).strip()
            if rel.endswith(".tex"):
                rel = rel[:-4]
            sub = os.path.dirname(rel)
            if not sub:
                continue
            target = os.path.normpath(os.path.join(builddir, sub))
            # 防目录逃逸
            if not (target + os.sep).startswith(os.path.abspath(builddir) + os.sep) \
               and target != os.path.abspath(builddir):
                target = os.path.join(os.path.abspath(builddir),
                                      os.path.basename(sub))
            os.makedirs(target, exist_ok=True)
            if target not in made:
                made.append(target)
    return made


def aux_hash(builddir):
    """构建目录内全部 .aux 内容的联合哈希。"""
    h = hashlib.sha256()
    for root, _dirs, files in os.walk(builddir):
        for fn in sorted(files):
            if fn.endswith(".aux"):
                p = os.path.join(root, fn)
                h.update(os.path.relpath(p, builddir).encode("utf-8"))
                with open(p, "rb") as f:
                    h.update(f.read())
    return h.hexdigest()


def run_cmd(cmd, cwd, env=None, timeout=180):
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.stdout.decode("utf-8", errors="replace")
        return proc.returncode, out, round(time.time() - t0, 2)
    except FileNotFoundError:
        return 127, "command not found: %s" % cmd[0], 0.0
    except subprocess.TimeoutExpired:
        return 124, "timeout after %ds" % timeout, float(timeout)


def main():
    ap = argparse.ArgumentParser(description="LaTeX 工程探测与有界多轮编译")
    ap.add_argument("--project", required=True, help="LaTeX 工程目录")
    ap.add_argument("--builddir", required=True, help="独立构建目录")
    ap.add_argument("--report", default=None, help="构建报告 JSON 输出路径")
    ap.add_argument("--engine", choices=["pdflatex", "xelatex"], default=None,
                    help="强制指定引擎（默认自动判定）")
    ap.add_argument("--max-rounds", type=int, default=4, help="引擎最多轮数")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    builddir = os.path.abspath(args.builddir)
    os.makedirs(builddir, exist_ok=True)
    t_start = time.time()
    t_start_ns = os.stat(builddir).st_mtime_ns  # 占位，后面用 time.time_ns
    t_start_ns = time.time_ns()

    report = {
        "tool": "texbuild.py",
        "project": project,
        "builddir": builddir,
        "status": "failed",
        "blocked_reason": None,
        "missing_tools": [],
        "main_file": None,
        "engine": None,
        "bib_tool": None,
        "mirrored_dirs": [],
        "preflight_missing_packages": [],
        "preflight_note": None,
        "rounds": [],
        "converged": False,
        "convergence": None,
        "log": None,
        "pdf": None,
        "pdf_bytes": None,
        "pdf_fresh": False,
        "error_lines_in_final_log": None,
        "rerun_hint_in_final_log": False,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    def finish(code):
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        if args.report:
            os.makedirs(os.path.dirname(os.path.abspath(args.report)),
                        exist_ok=True)
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return code

    # ---- 1. 工程探测 ----
    main_rel = find_main_file(project)
    if main_rel is None:
        report["status"] = "failed"
        report["blocked_reason"] = "工程中未找到含 \\documentclass 的主 .tex 文件"
        log_msg(report["blocked_reason"])
        return finish(4)
    report["main_file"] = main_rel
    main_stem = os.path.splitext(os.path.basename(main_rel))[0]

    engine = args.engine or detect_engine(project)
    report["engine"] = engine
    bib_tool = detect_bib_tool(project)
    report["bib_tool"] = bib_tool

    # ---- 2. 外部工具探测（诚实 blocked）----
    missing = []
    if shutil.which(engine) is None:
        missing.append(engine)
    if bib_tool and shutil.which(bib_tool) is None:
        missing.append(bib_tool)
    if missing:
        report["status"] = "blocked"
        report["missing_tools"] = missing
        report["blocked_reason"] = (
            "缺少外部编译工具：%s。需要安装 TeX Live（提供 pdflatex/xelatex/"
            "bibtex/biber）并把其 bin 目录加入 PATH 后重试；本脚本不伪造编译结果。"
            % ", ".join(missing))
        log_msg(report["blocked_reason"])
        return finish(3)

    # ---- 3. 宏包预检 + 构建目录子目录镜像 + 删除旧 PDF ----
    pre_missing, pre_note = preflight_missing_packages(project)
    report["preflight_missing_packages"] = pre_missing
    report["preflight_note"] = pre_note
    if pre_missing:
        log_msg("预检发现未安装宏包/类：%s（编译可能因此 Emergency stop）"
                % ", ".join(p["file"] for p in pre_missing))
    report["mirrored_dirs"] = [os.path.relpath(d, builddir)
                               for d in mirror_include_dirs(project, builddir)]
    pdf_path = os.path.join(builddir, main_stem + ".pdf")
    if os.path.exists(pdf_path):
        os.remove(pdf_path)  # 绝不用旧 PDF 冒充成功
        log_msg("已删除旧 PDF：%s" % pdf_path)

    log_path = os.path.join(builddir, main_stem + ".log")
    env = dict(os.environ)
    env["TEXINPUTS"] = project + os.pathsep + env.get("TEXINPUTS", "")
    env["BIBINPUTS"] = project + os.pathsep + env.get("BIBINPUTS", "")
    env["max_print_line"] = str(MAX_PRINT_LINE)  # 保持可解析的 79 列包裹

    prev_aux = None
    bib_done = False
    errors_seen = 0
    rerun_hint = False

    # ---- 4. 有界多轮编译 ----
    for rnd in range(1, max(1, args.max_rounds) + 1):
        cmd = [engine, "-interaction=nonstopmode",
               "-output-directory", builddir, main_rel]
        rc, out, secs = run_cmd(cmd, cwd=project, env=env)
        round_rec = {"round": rnd, "cmd": " ".join(cmd),
                     "returncode": rc, "seconds": secs}
        log_text = read_text(log_path)
        merged = unwrap_lines(log_text)
        errors_seen = sum(1 for ln in merged if ln.startswith("! "))
        rerun_hint = bool(RE_RERUN.search(log_text))
        round_rec["error_lines"] = errors_seen
        round_rec["rerun_hint"] = rerun_hint

        # 文献工具：首轮之后按需执行一次（之后若引用仍未稳定会在后续轮再补）
        if bib_tool and not bib_done and rnd == 1:
            bst_or_bcf = (main_stem + ".bcf") if bib_tool == "biber" \
                         else (main_stem + ".aux")
            if os.path.exists(os.path.join(builddir, bst_or_bcf)):
                brc, bout, bsecs = run_cmd([bib_tool, main_stem],
                                           cwd=builddir, env=env)
                round_rec["bib"] = {"tool": bib_tool, "returncode": brc,
                                    "seconds": bsecs}
                bib_done = True
                rerun_hint = True  # 文献工具后必须再跑引擎

        cur_aux = aux_hash(builddir)
        round_rec["aux_sha256"] = cur_aux[:16]
        report["rounds"].append(round_rec)

        if prev_aux is not None and cur_aux == prev_aux and not rerun_hint:
            report["converged"] = True
            report["convergence"] = ("第 %d 轮与第 %d 轮 aux 哈希一致且无 Rerun 提示"
                                     % (rnd - 1, rnd))
            break
        prev_aux = cur_aux

    if not report["converged"]:
        report["convergence"] = ("达到轮数上限 %d 仍未收敛（aux 变化或存在 "
                                 "Rerun 提示）" % args.max_rounds)

    # ---- 5. PDF 新鲜度校验 ----
    pdf_ok = False
    if os.path.exists(pdf_path):
        pdf_ok = os.stat(pdf_path).st_mtime_ns >= t_start_ns
    report["pdf"] = pdf_path if os.path.exists(pdf_path) else None
    report["pdf_bytes"] = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else None
    report["pdf_fresh"] = pdf_ok
    report["log"] = log_path if os.path.exists(log_path) else None
    report["error_lines_in_final_log"] = errors_seen
    report["rerun_hint_in_final_log"] = rerun_hint

    if not os.path.exists(pdf_path):
        report["status"] = "failed"
        report["blocked_reason"] = "编译未产出 PDF（可能存在致命错误），详见日志解析"
        return finish(1)
    if not pdf_ok:
        report["status"] = "failed"
        report["blocked_reason"] = ("构建目录中存在 PDF 但其修改时间早于本次构建，"
                                    "判定为陈旧产物，拒绝采信")
        return finish(1)
    if errors_seen > 0:
        report["status"] = "latex_errors"
        return finish(1)
    report["status"] = "success"
    return finish(0)


if __name__ == "__main__":
    sys.exit(main())
