#!/usr/bin/env python3
"""make_result.py — 汇总产物，生成符合 case.json output_contract 的 result.json。

- output_contract 字段列表运行时从 case.json 读取，不硬编码；
  另加 uncertainties、change_records（COMMON_SPEC §0）。
- compliance_checks 的 actual 全部来自脚本真实测量（python-pptx 读 pptx、
  soffice 真实渲染、convergence.json 真实判定），禁止凭空断言。
- 渲染降级链：soffice -> rendered=false + exceptions 记 tool_missing。

用法：
  make_result.py --case case.json --task task.md --deck deck_v2.json \
      --pptx presentation.pptx --build-report build_report.json \
      --convergence convergence.json [--ledger tribunal.json] \
      [--fixes fixes_report.json] [--facts facts.json] --outdir OUTPUT_DIR
退出码：0 result.json 写出；2 输入错误。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

SOFFICE_CANDIDATES = [
    "soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
]
DEFAULT_PLACEHOLDER_PATTERNS = re.compile(
    r"click to (add|edit)|单击此处|lorem ipsum", re.IGNORECASE)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_soffice():
    for c in SOFFICE_CANDIDATES:
        if shutil.which(c) or os.path.isfile(c):
            return c
    return None


def render(pptx_path, outdir, profile_key, exceptions):
    """soffice -> PDF -> PNG。返回 export_artifact 字段值。"""
    artifact = {"pdf": None, "rendered": False, "previews": [], "pages": 0}
    soffice = find_soffice()
    if not soffice:
        exceptions.append({"kind": "tool_missing",
                           "detail": "soffice 不可用，无法渲染 PDF/PNG 预览"})
        return artifact
    env_profile = f"-env:UserInstallation=file:///tmp/lo-{profile_key}"
    try:
        r = subprocess.run(
            [soffice, "--headless", env_profile, "--convert-to", "pdf",
             "--outdir", outdir, pptx_path],
            capture_output=True, text=True, timeout=300)
        pdf = os.path.join(outdir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
        if r.returncode != 0 or not os.path.isfile(pdf):
            exceptions.append({"kind": "render_failed",
                               "detail": f"soffice 退出码 {r.returncode}: {r.stderr.strip()[:300]}"})
            return artifact
        artifact["pdf"] = pdf
        artifact["rendered"] = True
    except Exception as e:
        exceptions.append({"kind": "render_failed", "detail": f"soffice 异常: {e}"})
        return artifact

    # PDF 页数（软导入降级链 pymupdf -> pypdf）
    try:
        import fitz
        doc = fitz.open(pdf)
        artifact["pages"] = doc.page_count
        doc.close()
    except ImportError:
        try:
            from pypdf import PdfReader
            artifact["pages"] = len(PdfReader(pdf).pages)
        except ImportError:
            exceptions.append({"kind": "tool_missing",
                               "detail": "pymupdf/pypdf 均缺失，PDF 页数未知"})
        except Exception as e:
            exceptions.append({"kind": "measure_failed", "detail": f"PDF 页数读取失败: {e}"})
    except Exception as e:
        exceptions.append({"kind": "measure_failed", "detail": f"PDF 页数读取失败: {e}"})

    # pdftoppm 预览
    if shutil.which("pdftoppm"):
        prefix = os.path.join(outdir, "preview")
        try:
            r = subprocess.run(["pdftoppm", "-png", "-r", "100", pdf, prefix],
                               capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                artifact["previews"] = sorted(
                    os.path.join(outdir, f) for f in os.listdir(outdir)
                    if f.startswith("preview") and f.endswith(".png"))
            else:
                exceptions.append({"kind": "render_failed",
                                   "detail": f"pdftoppm 退出码 {r.returncode}"})
        except Exception as e:
            exceptions.append({"kind": "render_failed", "detail": f"pdftoppm 异常: {e}"})
    else:
        exceptions.append({"kind": "tool_missing", "detail": "pdftoppm 不可用，无 PNG 预览"})
    return artifact


def parse_max_slides(task_text):
    m = re.search(r"[≤<]\s*(?:=)?\s*(\d+)\s*页", task_text)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:max|maximum|no more than|at most)\s+(\d+)\s+slides", task_text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:页|slides)", task_text, re.I)
    return int(m.group(1)) if m else None


def inspect_pptx(pptx_path, exceptions):
    """真实测量：页数、空/默认占位符数、各页备注有无。"""
    info = {"slides": None, "placeholder_violations": None, "notes_present": None}
    try:
        from pptx import Presentation
    except ImportError:
        exceptions.append({"kind": "tool_missing",
                           "detail": "python-pptx 缺失，无法测量 pptx 内部结构"})
        return info
    prs = Presentation(pptx_path)
    info["slides"] = len(prs.slides)
    violations = 0
    notes_flags = []
    for s in prs.slides:
        for ph in s.placeholders:
            try:
                txt = ph.text_frame.text if ph.has_text_frame else ""
            except Exception:
                txt = ""
            if not txt.strip() or DEFAULT_PLACEHOLDER_PATTERNS.search(txt):
                violations += 1
        try:
            nt = s.notes_slide.notes_text_frame.text.strip() if s.has_notes_slide else ""
        except Exception:
            nt = ""
        notes_flags.append(bool(nt))
    info["placeholder_violations"] = violations
    info["notes_present"] = notes_flags
    return info


def build_content_map(deck, facts, notes_flags):
    """content_map：sources 带逐字 quote；quote 命中情况如实标注。"""
    pages_text = ""
    if facts:
        pages_text = re.sub(r"\s+", " ",
                            " ".join(p["text"] for p in facts.get("pages", []))).strip()
    cap_labels = {c["label"] for c in (facts or {}).get("captions", [])}
    cmap = []
    for i, s in enumerate(deck.get("slides", [])):
        sources = []
        for claim in s.get("claims", []):
            for src in claim.get("sources", []):
                entry = {"kind": src.get("kind"), "ref": src.get("ref"),
                         "locator": src.get("locator"), "quote": src.get("quote")}
                if src.get("quote") and pages_text:
                    q = re.sub(r"\s+", " ", src["quote"]).strip()
                    entry["quote_verbatim"] = q in pages_text
                sources.append(entry)
        figs = []
        for label in s.get("figures", []) or []:
            figs.append({"label": label, "in_caption_index": label in cap_labels})
        notes_present = bool(s.get("notes", "").strip())
        if notes_flags is not None and i < len(notes_flags):
            notes_present = notes_flags[i]  # 以 pptx 实测为准
        cmap.append({
            "slide": s.get("slide"),
            "role": s.get("role"),
            "title": s.get("title"),
            "claims": [c.get("text", "") for c in s.get("claims", [])],
            "figures": figs,
            "table": s.get("table"),
            "sources": sources,
            "notes_present": notes_present,
            "notes_time_sec": s.get("notes_time_sec", 0),
        })
    return cmap


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成符合 output_contract 的 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--deck", required=True, help="最终 deck.json")
    ap.add_argument("--pptx", required=True)
    ap.add_argument("--build-report", required=True)
    ap.add_argument("--convergence", required=True)
    ap.add_argument("--ledger")
    ap.add_argument("--fixes")
    ap.add_argument("--facts")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--profile-key", default="d", help="soffice profile 隔离 key")
    args = ap.parse_args(argv)

    try:
        case = load_json(args.case)
        deck = load_json(args.deck)
        build = load_json(args.build_report)
        convergence = load_json(args.convergence)
        with open(args.task, encoding="utf-8") as f:
            task_text = f.read()
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 无法读取输入: {e}", file=sys.stderr)
        return 2
    facts = load_json(args.facts) if args.facts and os.path.isfile(args.facts) else None
    ledger = load_json(args.ledger) if args.ledger and os.path.isfile(args.ledger) else None
    fixes = load_json(args.fixes) if args.fixes and os.path.isfile(args.fixes) else None

    os.makedirs(args.outdir, exist_ok=True)
    exceptions = []

    t0 = time.time()
    artifact = render(args.pptx, args.outdir, args.profile_key, exceptions)
    render_sec = round(time.time() - t0, 1)

    pptx_info = inspect_pptx(args.pptx, exceptions)
    content_map = build_content_map(deck, facts, pptx_info["notes_present"])

    n_deck = len(deck.get("slides", []))
    n_pptx = pptx_info["slides"]
    max_slides = parse_max_slides(task_text)

    # evidence_coverage：claims 中至少一个 source 的比例（真实计数）
    total_claims = 0
    sourced = 0
    for s in deck.get("slides", []):
        for c in s.get("claims", []):
            total_claims += 1
            if c.get("sources"):
                sourced += 1
    evidence_cov = round(sourced / total_claims, 3) if total_claims else 1.0
    notes_cov = round(
        sum(1 for s in content_map if s["notes_present"]) / len(content_map), 3
    ) if content_map else 0.0
    notes_time_total = sum(s.get("notes_time_sec", 0) for s in content_map)

    pv = pptx_info["placeholder_violations"]
    checks = []
    checks.append({
        "check": "slide_count",
        "expected": f"<={max_slides}" if max_slides else "unknown",
        "actual": n_deck,
        "pass": (max_slides is not None and n_deck <= max_slides),
    })
    pages = artifact["pages"]
    checks.append({
        "check": "export_page_match",
        "expected": f"pdf_pages==pptx_slides({n_pptx})",
        "actual": pages if artifact["rendered"] else "not_rendered",
        "pass": bool(artifact["rendered"] and pages == n_pptx),
    })
    checks.append({
        "check": "placeholder_free",
        "expected": 0,
        "actual": pv if pv is not None else "unmeasured",
        "pass": pv == 0,
    })
    checks.append({
        "check": "evidence_coverage",
        "expected": 1.0,
        "actual": evidence_cov,
        "pass": evidence_cov == 1.0,
    })
    checks.append({
        "check": "notes_coverage",
        "expected": 1.0,
        "actual": notes_cov,
        "pass": notes_cov == 1.0,
    })
    checks.append({
        "check": "notes_time_total",
        "expected": "<=600",
        "actual": notes_time_total,
        "pass": notes_time_total <= 600,
    })
    checks.append({
        "check": "redteam_converged",
        "expected": "pass",
        "actual": convergence.get("verdict"),
        "pass": convergence.get("verdict") == "pass",
    })

    # change_records 来自台账 fixed 条目 + apply_fixes 报告
    change_records = []
    if ledger:
        for e in ledger.get("entries", {}).values():
            if e.get("status") == "fixed":
                last_fix = next((h for h in reversed(e["history"])
                                 if h["action"] in ("fix", "auto-fix")), None)
                change_records.append({
                    "version": "v1->v2",
                    "slide": e.get("slide"),
                    "change": f"[{e['rule']}] {(last_fix or {}).get('note', '')}",
                    "reason": e.get("suggested_fix", ""),
                    "rollback": "deck_v1.json 与 findings_round1.json 均已归档，可重跑 redteam_scan 复现",
                })
            elif e.get("status") == "dispositioned":
                d = e.get("disposition") or {}
                change_records.append({
                    "version": "v1->v2",
                    "slide": e.get("slide"),
                    "change": f"[{e['rule']}] disposition={d.get('type')}",
                    "reason": d.get("reason", ""),
                    "rollback": "撤销裁决需重新 open 该条目并复扫",
                })

    uncertainties = [
        "R4 栏目名标题为启发式判定，短标题且含数字时可能漏报，长标题可能误报",
        "R1 数值锚点按'数字+单位'精确匹配，论文中换行/上下标数值可能漏入事实池",
        "R3 逐字匹配依赖 PDF 文本层质量；扫描件 PDF 会整体退化为无法校验",
    ]
    if facts and facts.get("engine") != "pdftotext":
        uncertainties.append(f"PDF 文本提取走了降级引擎 {facts.get('engine')}")

    all_pass = all(c["pass"] for c in checks)
    status = "success" if (all_pass and artifact["rendered"]) else (
        "partial" if n_pptx else "failed")

    # 按 output_contract 原字段名组装（运行时读取，不硬编码）
    contract = case.get("output_contract", [])
    values = {
        "case_id": case.get("case_id"),
        "status": status,
        "editable_source": {
            "path": args.pptx,
            "format": "pptx",
            "slides": n_pptx,
            "notes_present": notes_cov == 1.0,
        },
        "export_artifact": artifact,
        "content_map": content_map,
        "compliance_checks": checks,
        "exceptions": exceptions,
    }
    result = {}
    missing = []
    for field in contract:
        if field in values:
            result[field] = values[field]
        else:
            result[field] = None
            missing.append(field)
    if missing:
        result.setdefault("exceptions", []).append(
            {"kind": "contract_field_unknown",
             "detail": f"output_contract 中未识别的字段: {missing}"})
    result["uncertainties"] = uncertainties
    result["change_records"] = change_records

    out_path = os.path.join(args.outdir, "result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"status={status} checks_pass={sum(1 for c in checks if c['pass'])}/{len(checks)} "
          f"rendered={artifact['rendered']} render_sec={render_sec} "
          f"redteam={convergence.get('verdict')} -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
