#!/usr/bin/env python3
"""plan_gate.py — S5 计划门禁。

校验 /app/work/slide_plan.json：
  1. JSON schema（stdlib 手写校验，无第三方依赖）；
  2. 页型覆盖 title → conclusion（且含 method/results）；
  3. 每页 evidence 锚点可解析到 S2 抽取产物（页存在、quote 逐字命中该页、图标签存在）；
  4. bullets/claim 中的数字 token 必须在源文逐字出现（空白归一化后比对）。

失败：写 /app/work/gates/plan_gate.json 明细，抛出 StageFailure（非零退出），
打印每一处违规的 slide/bullet 定位。通过：同样落盘，供 S8 汇总。
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stage_machine as sm
from stage_machine import StageFailure, now_iso, read_json, write_json

NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
ALLOWED_KINDS = {"title", "background", "method", "results", "discussion", "conclusion"}
ALLOWED_EVIDENCE_TYPES = {"page", "figure", "table", "section"}


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def norm_nospace(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _token_in_text(token: str, page_texts_ws, combined_ws, combined_ns) -> bool:
    token = token.strip()
    if not token:
        return True
    if token in combined_ws:
        return True
    # 兜底：PDF 抽取可能把数字拆行/加空格
    if norm_nospace(token) in combined_ns:
        return True
    return False


def run(ctx) -> list:
    plan_path = os.path.join(ctx.work, "slide_plan.json")
    extract_path = os.path.join(ctx.work, "paper", "extract.json")
    plan = read_json(plan_path)
    if not isinstance(plan, dict):
        raise StageFailure(
            f"slide_plan.json 不存在或不是合法 JSON 对象: {plan_path}",
            hint=f"先运行 prepare 生成骨架，再编辑 {plan_path}，最后 {ctx.default_resume_cmd()}")
    extract = read_json(extract_path)
    if not isinstance(extract, dict):
        raise StageFailure("缺少 S2 抽取产物 extract.json", hint=ctx.default_resume_cmd())

    page_texts = {}
    for i, pt in enumerate(extract.get("page_text_files", [])):
        try:
            with open(pt, "r", encoding="utf-8") as fh:
                page_texts[i + 1] = fh.read()
        except OSError:
            page_texts[i + 1] = ""
    combined_ws = norm_ws("\n".join(page_texts.values()))
    combined_ns = norm_nospace(combined_ws)
    fig_labels = set()
    for fg in extract.get("figures", []):
        lab = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(fg.get("label", "")).lower())
        fig_labels.add(lab)

    errors = []           # [{slide, where, problem}]
    ev_errors = []        # evidence-anchors-resolve 子门禁
    num_errors = []       # numbers-verbatim-vs-source 子门禁

    slides = plan.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append({"slide": None, "where": "schema", "problem": "slides 必须是非空数组"})
        slides = []
    if not isinstance(plan.get("mainline"), dict) or \
            any(k not in (plan.get("mainline") or {}) for k in ("problem", "method", "results", "limitations")):
        errors.append({"slide": None, "where": "schema",
                       "problem": "mainline 必须含 problem/method/results/limitations 四键"})
    if not (3 <= len(slides) <= 40):
        errors.append({"slide": None, "where": "schema",
                       "problem": f"slides 数量 {len(slides)} 超出 [3,40] 合理范围"})

    kinds = [s.get("kind") for s in slides if isinstance(s, dict)]
    for i, s in enumerate(slides):
        if not isinstance(s, dict):
            errors.append({"slide": i + 1, "where": "schema", "problem": "slide 必须是对象"})
            continue
        for key in ("kind", "title", "bullets", "figures", "evidence", "notes"):
            if key not in s:
                errors.append({"slide": i + 1, "where": "schema", "problem": f"缺字段 {key}"})
        if s.get("kind") not in ALLOWED_KINDS:
            errors.append({"slide": i + 1, "where": "schema",
                           "problem": f"非法 kind: {s.get('kind')!r}（允许 {sorted(ALLOWED_KINDS)}）"})
        if not isinstance(s.get("bullets"), list) or not all(isinstance(b, str) for b in s.get("bullets", [])):
            errors.append({"slide": i + 1, "where": "schema", "problem": "bullets 必须是字符串数组"})
        if not isinstance(s.get("evidence"), list):
            errors.append({"slide": i + 1, "where": "schema", "problem": "evidence 必须是数组"})

    if kinds:
        if kinds[0] != "title":
            errors.append({"slide": 1, "where": "coverage", "problem": "第一页必须是 title"})
        if kinds[-1] != "conclusion":
            errors.append({"slide": len(kinds), "where": "coverage", "problem": "最后一页必须是 conclusion"})
        for need in ("method", "results"):
            if need not in kinds:
                errors.append({"slide": None, "where": "coverage", "problem": f"缺少 {need} 页"})

    # 每页证据锚点 + 数字逐字
    for i, s in enumerate(slides):
        if not isinstance(s, dict):
            continue
        n = i + 1
        evs = s.get("evidence") if isinstance(s.get("evidence"), list) else []
        if not evs:
            ev_errors.append({"slide": n, "where": "evidence", "problem": "本页没有任何 evidence 锚点"})
        for j, ev in enumerate(evs):
            if not isinstance(ev, dict):
                ev_errors.append({"slide": n, "where": f"evidence[{j}]", "problem": "锚点必须是对象"})
                continue
            etype, eref, equote = ev.get("type"), str(ev.get("ref", "")), str(ev.get("quote", ""))
            if etype not in ALLOWED_EVIDENCE_TYPES:
                ev_errors.append({"slide": n, "where": f"evidence[{j}]",
                                  "problem": f"非法 evidence type: {etype!r}"})
                continue
            if etype == "page":
                m = re.search(r"(\d+)", eref)
                pno = int(m.group(1)) if m else None
                if not pno or not (1 <= pno <= extract.get("pages", 0)):
                    ev_errors.append({"slide": n, "where": f"evidence[{j}]",
                                      "problem": f"页码 {eref!r} 超出源文范围 1..{extract.get('pages')}"})
                    continue
                if len(norm_ws(equote)) < 8:
                    ev_errors.append({"slide": n, "where": f"evidence[{j}]",
                                      "problem": "page 锚点的 quote 太短（<8 字符），无法逐字核验"})
                    continue
                page_ws = norm_ws(page_texts.get(pno, ""))
                if norm_ws(equote) not in page_ws and norm_nospace(equote) not in norm_nospace(page_ws):
                    ev_errors.append({"slide": n, "where": f"evidence[{j}]",
                                      "problem": f"quote 未逐字出现在 p.{pno}: {equote[:60]!r}"})
            elif etype == "figure":
                lab = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", eref.lower())
                if lab not in fig_labels and norm_ws(eref).lower() not in combined_ws.lower():
                    ev_errors.append({"slide": n, "where": f"evidence[{j}]",
                                      "problem": f"图标签 {eref!r} 既不在抽取的图清单也不在源文中"})
            else:  # table / section
                if len(norm_ws(eref)) < 2 or (norm_ws(eref) not in combined_ws
                                              and norm_nospace(eref) not in combined_ns):
                    ev_errors.append({"slide": n, "where": f"evidence[{j}]",
                                      "problem": f"{etype} 引用 {eref!r} 未在源文中找到"})
        # 图文件必须真实存在
        for j, fg in enumerate(s.get("figures") or []):
            if not isinstance(fg, dict) or not fg.get("path"):
                ev_errors.append({"slide": n, "where": f"figures[{j}]", "problem": "figure 缺 path"})
                continue
            if not os.path.isfile(fg["path"]):
                ev_errors.append({"slide": n, "where": f"figures[{j}]",
                                  "problem": f"图文件不存在: {fg['path']}"})
        # 数字逐字
        for where, text in [(f"bullets[{k}]", b) for k, b in enumerate(s.get("bullets") or [])] + \
                           [("claim", s.get("claim") or "")]:
            for tok in NUM_RE.findall(text or ""):
                if not _token_in_text(tok, page_texts, combined_ws, combined_ns):
                    num_errors.append({"slide": n, "where": where,
                                       "problem": f"数字 {tok!r} 未在源文中逐字出现",
                                       "context": text[:120]})

    errors.extend(ev_errors)
    errors.extend(num_errors)
    gates = {
        "evidence-anchors-resolve": {
            "status": "fail" if ev_errors else "pass",
            "detail": (f"{len(ev_errors)} 处证据锚点无法解析" if ev_errors
                       else "全部 evidence 锚点均可解析到抽取产物（页/图/表/章节 + 逐字 quote）"),
        },
        "numbers-verbatim-vs-source": {
            "status": "fail" if num_errors else "pass",
            "detail": (f"{len(num_errors)} 个数字 token 未在源文逐字出现" if num_errors
                       else "bullets/claim 中全部数字 token 均与源文逐字一致（空白归一化）"),
        },
    }
    rec = {
        "plan": plan_path,
        "extract": extract_path,
        "gates": gates,
        "errors": errors,
        "checked_at": now_iso(),
        "slides_checked": len(slides),
    }
    out = os.path.join(ctx.gates_dir, "plan_gate.json")
    write_json(out, rec)
    # partial-first：S5 结果立即反映到交付侧 qa_gates.json
    for g, info in gates.items():
        sm.save_gate(ctx, g, info["status"], out, info["detail"])

    if errors:
        print(f"[S5] plan-gate 未通过，{len(errors)} 处问题：", flush=True)
        for e in errors[:40]:
            print(f"  slide {e.get('slide')} {e.get('where')}: {e.get('problem')}", flush=True)
        raise StageFailure(
            f"plan-gate 未通过：{len(errors)} 处问题（详见 {out}）",
            hint=f"按上方 slide/bullet 定位修复 {plan_path} 后重跑：{ctx.default_resume_cmd()}")
    print(f"[S5] plan-gate 通过：{len(slides)} 页，证据锚点与数字逐字核验 OK", flush=True)
    return [out]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="plan_gate.py", description="S5 计划门禁（独立调试入口）")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    ctx = sm.Ctx(args.input, args.work, args.output, "finish")
    try:
        run(ctx)
    except StageFailure as e:
        print(f"FAIL S5 plan-gate: {e}", flush=True)
        print(f"RESUME: {e.hint}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
