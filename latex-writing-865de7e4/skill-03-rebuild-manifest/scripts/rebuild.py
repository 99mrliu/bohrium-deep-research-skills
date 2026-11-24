#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rebuild.py — 模拟他人环境：按 manifest 在干净目录重建并比对一致性。

仅使用 Python3 标准库；pdflatex / bibtex / pdftotext 运行时探测，缺失时诚实降级。

流程：
  1. 用 zipfile 把工程源码打包成 zip（证明“打包-带走”这一步可行）；
  2. 解压到一个全新的干净目录，先逐文件比对 SHA256（注入 \\listfiles 之前）；
  3. 在解压副本的主文件中注入 \\listfiles（同 capture 的临时副本注入）；
  4. 按 manifest 记录的精确命令序列与轮次重放编译；
  5. 重新提取版本清单/引擎/轮次/aux 收敛/页数/全文文本哈希，逐项比对；
  6. 输出 rebuild_report.json 与 rebuild_report.md。

判定（诚实处理 PDF 字节不确定性）：
  - PDF 字节级不同（/ID、时间戳）属正常，不作为判据，只如实报告；
  - reproducible-identical 要求：源码逐文件 same + 版本清单无 different/missing
    + 引擎一致 + 轮次相同 + aux 收敛 + 页数一致 + 全文文本一致；
  - 任一宏包/类版本 different：逐条列出并判 not-reproducible-identical，
    不得含糊带过；
  - pdftotext 缺失导致文本无法比对：判 inconclusive 并说明。

用法：
  python3 rebuild.py --project /path/to/project \
      --manifest /app/work/manifest/manifest.json \
      --workdir /app/work/rebuild
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile

# 复用 capture.py 中的纯函数（同目录脚本，避免跨 bundle 引用）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402


def sha256_file(path):
    return capture.sha256_file(path)


def zip_project(project_dir, zip_path, inputs):
    """按 manifest 输入清单打包源码（zipfile 模块），返回实际打包的文件数。"""
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for e in inputs:
            src = os.path.join(project_dir, e["path"])
            if os.path.isfile(src):
                zf.write(src, e["path"])
                n += 1
    return n


def extract_zip(zip_path, dest_dir):
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            # 防目录穿越：拒绝绝对路径与 ..
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                continue
            zf.extract(info, dest_dir)


def compare_inputs(manifest_inputs, clean_dir):
    """逐文件比对源码哈希。返回 (rows, all_same)。"""
    rows = []
    all_same = True
    for e in manifest_inputs:
        p = os.path.join(clean_dir, e["path"])
        if not os.path.isfile(p):
            rows.append({"path": e["path"], "status": "missing",
                         "baseline_sha256": e["sha256"], "rebuild_sha256": None})
            all_same = False
            continue
        h = sha256_file(p)
        status = "same" if h == e["sha256"] else "changed"
        if status != "same":
            all_same = False
        rows.append({"path": e["path"], "status": status,
                     "baseline_sha256": e["sha256"], "rebuild_sha256": h})
    return rows, all_same


def compare_versions(baseline, rebuilt):
    """逐条目比对类/宏包版本清单：same / different / missing。

    missing 附 side 字段说明缺在哪一侧。
    """
    bmap = {e["file"]: e for e in baseline}
    rmap = {e["file"]: e for e in rebuilt}
    rows = []
    has_bad = False
    for fname in sorted(set(bmap) | set(rmap)):
        b = bmap.get(fname)
        r = rmap.get(fname)

        def key(e):
            return ((e or {}).get("date") or "", (e or {}).get("version") or "")
        if b and r:
            status = "same" if key(b) == key(r) else "different"
            side = None
        elif b:
            status, side = "missing", "absent-in-rebuild"
        else:
            status, side = "missing", "absent-in-baseline"
        if status != "same":
            has_bad = True
        rows.append({"file": fname, "status": status, "side": side,
                     "baseline": {"date": (b or {}).get("date"),
                                  "version": (b or {}).get("version")},
                     "rebuild": {"date": (r or {}).get("date"),
                                 "version": (r or {}).get("version")}})
    return rows, has_bad


def replay_steps(steps, clean_dir, tools, limitations):
    """按 manifest 记录的命令序列重放。工具缺失时跳过并如实降级。"""
    replayed = []
    for st in steps:
        tool = st["tool"]
        t = tools.get(tool)
        if not t:
            limitations.append("重建环境缺少 %s，跳过该步骤（原命令：%s）"
                               % (tool, " ".join(st["argv"])))
            replayed.append({"seq": st["seq"], "tool": tool, "argv": st["argv"],
                             "skipped": True})
            continue
        argv = [t["path"]] + list(st["argv"])
        res = capture.run_step(argv, clean_dir)
        replayed.append({"seq": st["seq"], "tool": tool, "argv": st["argv"],
                         "skipped": False,
                         **{k: res[k] for k in ("exit_code", "elapsed_s", "timed_out")}})
    return replayed


def write_report_md(report, path):
    r = report
    L = []
    L.append("# 异地重建一致性比对报告（人读版）")
    L.append("")
    L.append("> 本文件由 rebuild.py 自动生成，与 rebuild_report.json 内容一致。")
    L.append("")
    L.append("- 生成时间（UTC）：%s" % r["created_utc"])
    L.append("- **判定结论：`%s`**" % r["verdict"])
    L.append("- 判定说明：%s" % r["verdict_reason"])
    if r.get("limitations"):
        L.append("- 限制/降级说明：")
        for lim in r["limitations"]:
            L.append("  - %s" % lim)
    L.append("")
    L.append("## 判定细则汇总")
    L.append("")
    L.append("| 判据 | 结果 |")
    L.append("|------|------|")
    c = r["checks"]
    L.append("| 源码逐文件 SHA256 | %s |" % c["inputs"]["summary"])
    L.append("| 类/宏包版本清单 | %s |" % c["versions"]["summary"])
    L.append("| 引擎与发行版 | %s |" % c["engine"]["status"])
    L.append("| 编译轮次相同 | %s |" % ("是" if c["passes"]["same"] else "否"))
    L.append("| 重建后 aux 收敛 | %s |"
             % ({True: "是", False: "否", None: "未知"}[c["aux_converged"]["rebuild"]]))
    L.append("| PDF 页数一致 | %s |" % ({True: "是", False: "否", None: "不可比"}[c["pages"]["same"]]))
    L.append("| 全文文本一致 | %s |" % ({True: "是", False: "否", None: "不可比"}[c["text"]["same"]]))
    L.append("")
    L.append("## 关于 PDF 字节级差异（诚实声明）")
    L.append("")
    L.append("PDF 内含 /ID 与生成时间戳，即使输入与工具链完全一致，字节级哈希通常也不同，"
             "**不作为一致性判据**，此处仅如实报告：")
    L.append("")
    L.append("- 基线 PDF SHA256：`%s`" % (c["pdf_bytes"]["baseline_sha256"] or "—"))
    L.append("- 重建 PDF SHA256：`%s`" % (c["pdf_bytes"]["rebuild_sha256"] or "—"))
    L.append("- 字节级一致：%s（正常预期为否，不影响判定）"
             % ({True: "是", False: "否", None: "不可比"}[c["pdf_bytes"]["same"]]))
    L.append("")
    diff = [v for v in r["checks"]["versions"]["entries"] if v["status"] != "same"]
    L.append("## 版本清单差异条目（共 %d 条）" % len(diff))
    L.append("")
    if diff:
        L.append("| 文件 | 状态 | 基线版本 | 重建版本 |")
        L.append("|------|------|----------|----------|")
        for v in diff:
            bb = " ".join(x for x in [v["baseline"]["date"], v["baseline"]["version"]] if x) or "—"
            rr = " ".join(x for x in [v["rebuild"]["date"], v["rebuild"]["version"]] if x) or "—"
            L.append("| %s | %s%s | %s | %s |"
                     % (v["file"], v["status"],
                        "（%s）" % v["side"] if v["side"] else "", bb, rr))
    else:
        L.append("（无差异，全部 same）")
    L.append("")
    bad_inputs = [i for i in r["checks"]["inputs"]["entries"] if i["status"] != "same"]
    L.append("## 源码哈希不一致文件（共 %d 个）" % len(bad_inputs))
    L.append("")
    if bad_inputs:
        for i in bad_inputs:
            L.append("- %s：%s" % (i["path"], i["status"]))
    else:
        L.append("（全部 same）")
    L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description="按 manifest 在干净目录重建并比对一致性")
    ap.add_argument("--project", required=True, help="原始 LaTeX 工程目录（打包来源）")
    ap.add_argument("--manifest", required=True, help="capture.py 生成的 manifest.json")
    ap.add_argument("--workdir", default="/app/work/rebuild", help="重建工作目录")
    args = ap.parse_args()

    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    limitations = []
    report = {
        "report_version": "1.0",
        "kind": "latex-rebuild-report",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": "rebuild.py (latex-rebuild-manifest skill)",
        "verdict": "inconclusive",
        "verdict_reason": "",
        "limitations": limitations,
        "zip": None,
        "replay": [],
        "checks": {},
    }

    if not os.path.isfile(args.manifest):
        report["verdict"] = "inconclusive"
        report["verdict_reason"] = "manifest 不存在：%s" % args.manifest
        _emit(report, workdir)
        return 2
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    project_dir = os.path.abspath(args.project)
    if not os.path.isdir(project_dir):
        report["verdict"] = "inconclusive"
        report["verdict_reason"] = "工程目录不存在：%s" % project_dir
        _emit(report, workdir)
        return 2

    main_tex = manifest["project"]["main_tex"]
    jobname = os.path.splitext(os.path.basename(main_tex))[0]
    m_inputs = manifest.get("inputs", [])

    # 1) 打包 -> 2) 解压到干净目录
    zip_path = os.path.join(workdir, "source_snapshot.zip")
    n = zip_project(project_dir, zip_path, m_inputs)
    report["zip"] = {"path": zip_path, "files": n,
                     "note": "由 zipfile 模块生成；模拟把源码带到他人环境"}
    clean_dir = os.path.join(workdir, "rebuild_src")
    extract_zip(zip_path, clean_dir)

    # 3) 源码逐文件哈希比对（注入之前）
    input_rows, inputs_same = compare_inputs(m_inputs, clean_dir)
    n_bad = sum(1 for r in input_rows if r["status"] != "same")
    inputs_summary = "全部 same（%d 个）" % len(input_rows) if not n_bad else \
        "%d 个不一致/缺失（共 %d 个）" % (n_bad, len(input_rows))

    # 工具探测
    tools = {"pdflatex": capture.find_tool("pdflatex"),
             "bibtex": capture.find_tool("bibtex"),
             "pdftotext": capture.find_tool("pdftotext")}
    for name, t in tools.items():
        if not t:
            limitations.append("重建环境 %s 不可用" % name)

    # 4) 副本注入 \listfiles + 按 manifest 重放
    injected = False
    if tools["pdflatex"]:
        if os.path.isfile(os.path.join(clean_dir, main_tex)):
            injected = capture.inject_listfiles(clean_dir, main_tex)
            report["replay"] = replay_steps(manifest["build"]["steps"], clean_dir,
                                            tools, limitations)
        else:
            limitations.append("解压后的干净目录中缺少主文件 %s，无法重放编译" % main_tex)

    # 5) 重新取证
    log_path = os.path.join(clean_dir, jobname + ".log")
    log_text = ""
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            log_text = f.read()
    r_engine = capture.parse_engine(log_text) if log_text else None
    r_versions = capture.parse_file_list(log_text) if log_text else []
    r_pages = capture.parse_pages(log_text) if log_text else None
    r_aux_fp = capture.aux_fingerprint(clean_dir) if os.path.isdir(clean_dir) else None

    pdf_path = os.path.join(clean_dir, jobname + ".pdf")
    r_pdf_sha = sha256_file(pdf_path) if os.path.isfile(pdf_path) else None
    r_text_sha = r_text_chars = None
    text_note = None
    if os.path.isfile(pdf_path):
        r_text_sha, r_text_chars, text_note = capture.pdftotext_hash(pdf_path, tools["pdftotext"])
        if text_note:
            limitations.append("重建侧：%s" % text_note)

    # 6) 逐项比对
    ver_rows, ver_bad = compare_versions(manifest.get("file_versions", []), r_versions)
    n_diff = sum(1 for v in ver_rows if v["status"] == "different")
    n_miss = sum(1 for v in ver_rows if v["status"] == "missing")
    if not ver_rows:
        ver_summary = "两侧均为空，不可比"
    elif ver_bad:
        ver_summary = "%d different / %d missing（共 %d 条）" % (n_diff, n_miss, len(ver_rows))
    else:
        ver_summary = "全部 same（%d 条）" % len(ver_rows)

    b_eng = manifest.get("engine") or {}

    def eng_key(e):
        return ((e or {}).get("name"), (e or {}).get("version"), (e or {}).get("distribution"))
    if not b_eng.get("name") or not (r_engine or {}).get("name"):
        eng_status = "unknown"
    else:
        eng_status = "same" if eng_key(b_eng) == eng_key(r_engine) else "different"

    b_steps = [s for s in manifest["build"]["steps"] if s["tool"] == "pdflatex"]
    r_steps = [s for s in report["replay"] if s["tool"] == "pdflatex" and not s.get("skipped")]
    passes_same = len(b_steps) == len(r_steps)

    b_pages = manifest["build"].get("pdf_pages")
    pages_same = None if (b_pages is None or r_pages is None) else b_pages == r_pages

    b_text = (manifest.get("output_text") or {}).get("sha256")
    text_same = None if (not b_text or not r_text_sha) else b_text == r_text_sha

    b_pdf_sha = manifest["build"].get("pdf_sha256")
    pdf_same = None if (not b_pdf_sha or not r_pdf_sha) else b_pdf_sha == r_pdf_sha

    report["checks"] = {
        "inputs": {"summary": inputs_summary, "all_same": inputs_same, "entries": input_rows},
        "versions": {"summary": ver_summary, "has_different": n_diff > 0,
                     "has_missing": n_miss > 0, "entries": ver_rows},
        "engine": {"status": eng_status, "baseline": b_eng, "rebuild": r_engine},
        "passes": {"baseline": len(b_steps), "rebuild": len(r_steps), "same": passes_same},
        "aux_converged": {"baseline": manifest["build"].get("aux_converged"),
                          "rebuild": (r_aux_fp is not None and
                                      r_aux_fp == manifest["build"].get("aux_fingerprint"))},
        "pages": {"baseline": b_pages, "rebuild": r_pages, "same": pages_same},
        "text": {"baseline_sha256": b_text, "rebuild_sha256": r_text_sha,
                 "same": text_same,
                 "note": None if text_same is not None else
                         "pdftotext 缺失或编译失败，全文文本不可比"},
        "pdf_bytes": {"baseline_sha256": b_pdf_sha, "rebuild_sha256": r_pdf_sha,
                      "same": pdf_same,
                      "note": "PDF 含 /ID 与时间戳，字节级不同属正常，不作为判据"},
    }

    # 7) 判定
    if not tools["pdflatex"] or not os.path.isfile(pdf_path):
        report["verdict"] = "inconclusive"
        report["verdict_reason"] = "重建侧编译未完成（pdflatex 缺失或未生成 PDF），无法判定"
    elif not inputs_same:
        report["verdict"] = "not-reproducible-identical"
        report["verdict_reason"] = "源码哈希存在 changed/missing 文件，重建输入与基线不一致"
    elif n_diff > 0 or n_miss > 0 or eng_status == "different":
        bad = [v["file"] for v in ver_rows if v["status"] != "same"]
        reason = "版本清单存在差异条目：%s" % ("、".join(bad) if bad else "（无）")
        if eng_status == "different":
            reason += "；引擎/发行版不同（%s vs %s）" % (
                (b_eng.get("distribution") or "?"), ((r_engine or {}).get("distribution") or "?"))
        report["verdict"] = "not-reproducible-identical"
        report["verdict_reason"] = reason
    elif text_same is None:
        report["verdict"] = "inconclusive"
        report["verdict_reason"] = "全文文本不可比（pdftotext 缺失或一侧无 PDF），"
        report["verdict_reason"] += "其余判据：页数=%s，版本清单=%s" % (pages_same, ver_summary)
    elif text_same and pages_same and report["checks"]["aux_converged"]["rebuild"] \
            and passes_same:
        report["verdict"] = "reproducible-identical"
        report["verdict_reason"] = ("文本一致 + 页数一致 + aux 收敛 + 版本清单无 "
                                    "different/missing + 轮次相同（PDF 字节差异属正常，未计入）")
    else:
        report["verdict"] = "not-reproducible-identical"
        report["verdict_reason"] = ("文本/页数/aux 收敛/轮次中至少一项不一致：text=%s, "
                                    "pages=%s, aux=%s, passes=%s"
                                    % (text_same, pages_same,
                                       report["checks"]["aux_converged"]["rebuild"],
                                       passes_same))

    _emit(report, workdir)
    return 0


def _emit(report, workdir):
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, "rebuild_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    write_report_md(report, os.path.join(workdir, "rebuild_report.md"))
    print("[rebuild] verdict=%s -> %s" % (report["verdict"], workdir))


if __name__ == "__main__":
    sys.exit(main())
