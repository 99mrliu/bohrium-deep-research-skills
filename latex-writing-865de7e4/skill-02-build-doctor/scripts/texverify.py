#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
texverify.py — Agent 修复后的重编译验证与 result.json 装配（仅 Python3 标准库）。

流程（确定性机械工作）：
  1. 读取 case.json 并归一化 output_contract（四种历史方言：
     {字段:{type,required}} / 自然语言描述 / JSON Schema / 字段名列表）。
  2. 子进程调用 texbuild.py 做有界多轮重编译（独立构建目录，绝不信旧 PDF）。
  3. 子进程调用 texlog.py 解析新日志，要求 0 错误；收集警告清单。
  4. PDF 抽查：pdftotext 统计页数（\\f 计数，失败则回退 PDF 字节正则）、
     抽取首页文本做关键词抽查；pdftoppm 渲染首页 PNG 供目检。
     外部工具缺失时诚实降级并写入 uncertainty，不假装完成。
  5. 装配 result.json：case_id 原样复制；契约字段逐字段镜像（缺材料给
     null + uncertainty 说明，禁止编造）；status 据实；artifacts 只列真实
     存在的文件。

用法：
  python3 texverify.py --project <工程目录> --case <case.json> \
      --workdir </app/work/verify> --out </app/output> \
      [--task <task.md>] [--skill-dir <Skill 根目录>] \
      [--engine pdflatex|xelatex] [--max-rounds 4] [--expect 关键词1,关键词2]

退出码：0=complete；1=partial/failed；3=blocked；2=用法错误。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

RE_TITLE = re.compile(r"\\title\{([^}]*)\}")


def log_msg(msg):
    sys.stderr.write("[texverify] %s\n" % msg)


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def normalize_contract(raw):
    """output_contract 四种方言归一化 -> {字段: {required, hint}}。"""
    fields = {}
    notes = []
    if raw is None:
        return fields, ["case.json 无 output_contract，契约字段为空"]
    if isinstance(raw, list):  # 字段名列表
        for name in raw:
            if isinstance(name, str):
                fields[name] = {"required": True, "hint": ""}
        notes.append("契约方言：字段名列表")
    elif isinstance(raw, dict):
        if raw.get("type") == "object" and isinstance(
                raw.get("properties"), dict):  # JSON Schema
            req = set(raw.get("required") or [])
            for name, prop in raw["properties"].items():
                hint = prop.get("description", "") if isinstance(prop, dict) else ""
                fields[name] = {"required": name in req, "hint": hint}
            notes.append("契约方言：JSON Schema")
        elif all(isinstance(v, dict) and ("type" in v or "required" in v)
                 for v in raw.values()) and raw:  # {字段:{type,required}}
            for name, spec in raw.items():
                fields[name] = {"required": bool(spec.get("required", True)),
                                "hint": str(spec.get("type", ""))}
            notes.append("契约方言：{字段:{type,required}}")
        else:  # 自然语言描述 {字段: 描述}
            for name, desc in raw.items():
                d = desc if isinstance(desc, str) else json.dumps(
                    desc, ensure_ascii=False)
                optional = bool(re.search(r"可选|optional|非必需", d))
                fields[name] = {"required": not optional, "hint": d}
            notes.append("契约方言：自然语言描述")
    elif isinstance(raw, str):
        notes.append("契约为整段自然语言，无法拆字段，全部人工核对：" + raw[:200])
    else:
        notes.append("未知契约格式：%s" % type(raw).__name__)
    return fields, notes


def fill_field(name, ctx):
    """按字段名启发式镜像真实值；映射不上返回 (None, 原因)。"""
    n = name.lower()
    if re.search(r"pdf|compiled", n) and "count" not in n:
        return ctx.get("pdf_out"), None
    if re.search(r"page", n):
        return ctx.get("page_count"), None
    if re.search(r"diagnos|report", n):
        return ctx.get("diagnosis_md"), None
    if re.search(r"warn", n):
        return ctx.get("warnings"), None
    if re.search(r"error", n):
        return ctx.get("errors"), None
    if re.search(r"preview|png|render", n):
        return ctx.get("preview_png"), None
    if re.search(r"status", n):
        return ctx.get("status"), None
    return None, "契约字段 %r 无法由验证产物可靠映射，按诚实空值处理" % name


def pdf_page_count(pdf_path, pdftotext):
    """页数：优先 pdftotext 的 \\f 计数；否则回退 PDF 字节正则。"""
    if pdftotext:
        try:
            out = subprocess.run([pdftotext, pdf_path, "-"], timeout=60,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL).stdout
            text = out.decode("utf-8", errors="replace")
            n = text.count("\f")
            return (n if n > 0 else (1 if text.strip() else 0),
                    "pdftotext \\f 计数", text)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        with open(pdf_path, "rb") as f:
            blob = f.read()
        n = len(re.findall(rb"/Type\s*/Page[^s]", blob))
        return n, "PDF 字节正则回退（无 pdftotext）", None
    except OSError:
        return None, "无法读取 PDF", None


def run_script(script, argv):
    cmd = [sys.executable, script] + argv
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=600)
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace"), \
        proc.stderr.decode("utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser(description="修复后重编译验证与 result.json 装配")
    ap.add_argument("--project", required=True)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--workdir", default="/app/work/verify")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--skill-dir", default=None,
                    help="Skill 根目录（定位 scripts/ 与 references/；"
                         "默认为本脚本的上两级目录）")
    ap.add_argument("--engine", choices=["pdflatex", "xelatex"], default=None)
    ap.add_argument("--max-rounds", type=int, default=4)
    ap.add_argument("--expect", default=None,
                    help="首页应出现的关键词，逗号分隔（缺省用 \\title 推断）")
    args = ap.parse_args()

    skill_dir = os.path.abspath(args.skill_dir) if args.skill_dir else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    texbuild = os.path.join(skill_dir, "scripts", "texbuild.py")
    texlog = os.path.join(skill_dir, "scripts", "texlog.py")
    pkg_map = os.path.join(skill_dir, "references", "package-map.md")
    project = os.path.abspath(args.project)
    builddir = os.path.join(os.path.abspath(args.workdir), "build")
    diagdir = os.path.join(os.path.abspath(args.workdir), "diagnosis")
    outdir = os.path.abspath(args.out)
    for d in (builddir, diagdir, outdir):
        os.makedirs(d, exist_ok=True)

    uncertainty = []
    sources = []

    # ---- 1. case.json 与契约归一化 ----
    case_id, contract_fields = None, {}
    if os.path.exists(args.case):
        sources.append(os.path.abspath(args.case))
        try:
            case = json.loads(read_text(args.case))
            case_id = case.get("case_id")
            contract_fields, notes = normalize_contract(
                case.get("output_contract"))
            uncertainty.extend(n for n in notes if "无法" in n or "未知" in n)
        except ValueError as exc:
            uncertainty.append("case.json 解析失败：%s；按无契约降级" % exc)
    else:
        uncertainty.append("case.json 缺失（%s），case_id 置 null，"
                           "契约字段为空，按材料如实降级" % args.case)
    if os.path.exists(args.task):
        sources.append(os.path.abspath(args.task))

    result = {"case_id": case_id, "status": "failed"}
    result_path = os.path.join(outdir, "result.json")

    def write_result(ctx, artifacts):
        for name, spec in contract_fields.items():
            val, why = fill_field(name, ctx)
            result[name] = val
            if val is None and spec.get("required"):
                uncertainty.append("契约必填字段 %r 为 null：%s"
                                   % (name, why or "材料缺失"))
        result["sources"] = sorted(set(sources))
        result["uncertainty"] = uncertainty
        result["artifacts"] = [a for a in artifacts if a and os.path.exists(a)]
        result["assembled_by"] = "texverify.py（latex-build-doctor）"
        result["assembled_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log_msg("result.json 已落盘：%s（status=%s）"
                % (result_path, result["status"]))

    # ---- 2. 重编译（尽早落盘一版 result.json，再增量改进）----
    build_report = os.path.join(os.path.abspath(args.workdir),
                                "verify-build-report.json")
    tb_argv = ["--project", project, "--builddir", builddir,
               "--report", build_report, "--max-rounds", str(args.max_rounds)]
    if args.engine:
        tb_argv += ["--engine", args.engine]
    rc, out, err = run_script(texbuild, tb_argv)
    log_msg("texbuild 退出码 %d" % rc)
    try:
        build = json.loads(out)
    except ValueError:
        build = {"status": "failed",
                 "blocked_reason": "texbuild 输出不可解析", "rounds": []}
        uncertainty.append("texbuild 报告解析失败；stderr: %s" % err[:200])
    sources.append(build.get("log") or "")

    if build.get("status") == "blocked":
        result["status"] = "blocked"
        uncertainty.append(build.get("blocked_reason") or "缺少外部编译工具")
        write_result({"warnings": [], "errors": None}, [])
        return 3

    # ---- 3. 日志诊断（验证：0 错误）----
    diag_json = os.path.join(diagdir, "diagnosis.json")
    diag_md = os.path.join(diagdir, "diagnosis.md")
    errors_n, warn_list = None, []
    if build.get("log") and os.path.exists(build["log"]):
        rc2, out2, _err2 = run_script(
            texlog, ["--log", build["log"], "--project", project,
                     "--outdir", diagdir, "--map", pkg_map])
        log_msg("texlog 退出码 %d" % rc2)
        try:
            diag = json.loads(read_text(diag_json))
            errors_n = sum(r["count"] for r in diag.get("root_causes", [])
                           if r.get("severity") == "error")
            warn_list = [r["message"] for r in diag.get("root_causes", [])
                         if r.get("severity") == "warning"]
            warn_list += diag.get("warnings", [])[:20]
        except ValueError:
            uncertainty.append("diagnosis.json 不可读，错误数未知")
    else:
        uncertainty.append("无编译日志可解析")

    pdf = build.get("pdf")
    if not (pdf and os.path.exists(pdf) and build.get("pdf_fresh")):
        result["status"] = "failed"
        uncertainty.append("未获得本次构建的新鲜 PDF：" +
                           (build.get("blocked_reason") or "未知原因"))
        write_result({"warnings": warn_list, "errors": errors_n}, [])
        return 1

    # ---- 4. PDF 抽查：页数 / 首页关键词 / 渲染预览 ----
    pdf_out = os.path.join(outdir, os.path.basename(pdf))
    if os.path.abspath(pdf) != pdf_out:
        shutil.copy2(pdf, pdf_out)
    artifacts = [pdf_out]
    pdftotext = shutil.which("pdftotext")
    pdftoppm = shutil.which("pdftoppm")
    page_count, page_method, full_text = pdf_page_count(pdf_out, pdftotext)
    if not pdftotext:
        uncertainty.append("缺少 pdftotext，页数与文本抽查降级为：" + page_method)

    expect = []
    if args.expect:
        expect = [k.strip() for k in args.expect.split(",") if k.strip()]
    else:
        m = RE_TITLE.search(read_text(os.path.join(project,
                                                   build.get("main_file") or "")))
        if m:
            expect = [w for w in re.split(r"\s+", m.group(1)) if len(w) >= 3][:4]
    kw_check = None
    if full_text is not None and expect:
        first_page = full_text.split("\f")[0]
        kw_check = {k: (k in first_page) for k in expect}
        missing_kw = [k for k, ok in kw_check.items() if not ok]
        if missing_kw:
            uncertainty.append("首页关键词缺失：%s（请目检 PDF 首页）"
                               % ", ".join(missing_kw))
    elif expect:
        uncertainty.append("无 pdftotext，首页关键词抽查未执行：%s"
                           % ", ".join(expect))

    preview_png = None
    if pdftoppm:
        prefix = os.path.join(outdir, "preview")
        try:
            subprocess.run([pdftoppm, "-png", "-r", "120", "-f", "1", "-l", "1",
                            pdf_out, prefix], timeout=120,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            hits = sorted(glob.glob(prefix + "*.png"))
            if hits:
                preview_png = hits[0]
                artifacts.append(preview_png)
        except (OSError, subprocess.TimeoutExpired):
            uncertainty.append("pdftoppm 执行失败，首页预览未生成")
    else:
        uncertainty.append("缺少 pdftoppm，首页 PNG 预览未生成（降级，"
                           "不影响编译结论）")

    # 诊断报告随产物归档
    if os.path.exists(diag_md):
        dst = os.path.join(outdir, "diagnosis.md")
        shutil.copy2(diag_md, dst)
        diag_md = dst
        artifacts.append(diag_md)

    # ---- 5. 状态判定与装配 ----
    if errors_n == 0 and page_count:
        result["status"] = "complete"
    elif errors_n == 0:
        result["status"] = "partial"
        uncertainty.append("编译 0 错误但页数未能确认，标 partial")
    else:
        result["status"] = "partial"
        uncertainty.append("仍存在 %d 条错误，PDF 虽产出但不完全可信"
                           % (errors_n or -1))

    ctx = {"pdf_out": pdf_out, "page_count": page_count,
           "diagnosis_md": diag_md if os.path.exists(diag_md) else None,
           "warnings": warn_list, "errors": errors_n,
           "preview_png": preview_png, "status": result["status"]}
    result["verification"] = {
        "engine": build.get("engine"),
        "rounds": len(build.get("rounds", [])),
        "converged": build.get("converged"),
        "convergence": build.get("convergence"),
        "error_count": errors_n,
        "page_count": page_count,
        "page_count_method": page_method,
        "pdf_bytes": os.path.getsize(pdf_out),
        "first_page_keywords": kw_check,
        "preview_png": preview_png,
    }
    write_result(ctx, artifacts)
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
