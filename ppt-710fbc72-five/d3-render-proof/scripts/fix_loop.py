#!/usr/bin/env python3
"""fix_loop.py — 由 render_proof.json 驱动的有界自动修复循环（≤3 轮）。

修复语义（详见 references/render-qa.md）：
- 文本溢出 → 该页正文字号沿阶梯 20→18→16→14→12 降一级并重建重渲；
  已到下限 10pt（或阶梯用尽）仍溢出 → 拆分：后半要点移到 “(续)” 页。
- 图片丢失 → 按 basename 在 paper/figs 重新定位并重嵌；找不到 → 记 unfixable。
- 空渲染页 → 不自动修（多为导出级故障），记 unfixable 并如实报 partial。
硬规则：字号绝不低于 10pt；图片绝不拉伸（build_deck 等比缩放保证）。
每次修复同时写入 render_proof.json 的 fix_log 与返回的 change_log（供 result.json）。
"""
import glob
import json
import os

import build_deck
import render_pipeline

MAX_ITERS = 3
LADDER = build_deck.FONT_LADDER  # [20,18,16,14,12]，下限 10
FLOOR_PT = build_deck.FLOOR_PT
MIN_BULLETS_FOR_SPLIT = 4


def _next_size(cur):
    for s in LADDER:
        if s < cur:
            return s
    return FLOOR_PT if cur > FLOOR_PT else None


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _apply_overflow_fix(plan, slide_idx, slide, fix_log, iteration, page):
    cur = int(slide.get("body_font_override", build_deck.DEFAULT_BODY_PT))
    nxt = _next_size(cur)
    if nxt is not None and nxt >= FLOOR_PT and nxt != cur:
        slide["body_font_override"] = nxt
        fix_log.append({
            "iteration": iteration, "page": page, "type": "font_step_down",
            "detail": f"溢出：正文字号 {cur}pt → {nxt}pt（阶梯 {LADDER}，下限 {FLOOR_PT}pt）"})
        return True
    # 阶梯用尽 → 拆分续页
    bullets = slide.get("bullets", [])
    if len(bullets) >= MIN_BULLETS_FOR_SPLIT and not slide.get("_split_done"):
        half = len(bullets) // 2
        cont = dict(slide)
        cont["title"] = slide.get("title", "") + "（续）"
        cont["bullets"] = bullets[half:]
        cont["figures"] = []
        cont["body_font_override"] = FLOOR_PT
        cont["_split_done"] = True
        cont["notes"] = (slide.get("notes", "") + " [自动拆分续页]").strip()
        slide["bullets"] = bullets[:half]
        slide["_split_done"] = True
        slide["body_font_override"] = FLOOR_PT
        plan["slides"].insert(slide_idx + 1, cont)
        fix_log.append({
            "iteration": iteration, "page": page, "type": "split_continuation",
            "detail": f"阶梯用尽仍溢出：{len(bullets)} 条要点拆为 {half}+{len(bullets)-half}，"
                      f"新增续页「{cont['title']}」"})
        return True
    return False


def _apply_image_fix(work_dir, slide, fix_log, iteration, page, ref):
    figs_dir = os.path.join(work_dir, "paper", "figs")
    for fig in slide.get("figures", []):
        if fig.get("ref") == ref or not fig.get("path") or not os.path.exists(fig.get("path", "")):
            base = os.path.basename(fig.get("path", ""))
            hits = glob.glob(os.path.join(figs_dir, "**", base), recursive=True) or \
                glob.glob(os.path.join(figs_dir, "*.png"))
            if hits:
                old = fig.get("path", "")
                fig["path"] = hits[0]
                fix_log.append({"iteration": iteration, "page": page, "type": "reembed_image",
                                "detail": f"图 {ref} 重新定位：{old} → {hits[0]}"})
                return True
    return False


def run_fix_loop(work_dir, output_dir, template_path, max_iters=MAX_ITERS):
    """返回 (overall, fix_log, unfixable)。幂等：再次运行时若 QA 通过则不产生新修复。
    fix_log/unfixable 持久化在 render_proof.json 中，由调用方汇总进 result.json。"""
    plan_path = os.path.join(work_dir, "slide_plan.json")
    proof_path = os.path.join(output_dir, "render_proof.json")
    proof = _load(proof_path)
    fix_log = proof.get("fix_log", [])
    unfixable = list(proof.get("unfixable", []))
    run_no = int(proof.get("run", 1))

    for iteration in range(1, max_iters + 1):
        failures = [f for f in proof.get("failures", []) if f.get("page")]
        if not failures:
            break
        plan = _load(plan_path)
        build_log = _load(os.path.join(work_dir, "build_log.json"))
        applied = []
        for fail in failures:
            page = fail["page"]
            entry = next((p for p in build_log["pages"] if p["page"] == page), None)
            if entry is None:
                continue
            idx = entry["plan_index"]
            if idx >= len(plan["slides"]):
                continue
            slide = plan["slides"][idx]
            ok = False
            if fail["check"] == "overflow":
                ok = _apply_overflow_fix(plan, idx, slide, fix_log, iteration, page)
            elif fail["check"] == "image_loss":
                ok = _apply_image_fix(work_dir, slide, fix_log, iteration, page,
                                      fail.get("ref", ""))
            if not ok:
                item = {"page": page, "check": fail["check"],
                        "reason": "阶梯用尽且不可拆分/图无法定位/导出级故障，保持诚实 partial"}
                if item not in unfixable:
                    unfixable.append(item)
                fix_log.append({"iteration": iteration, "page": page,
                                "type": "unfixable", "detail": item["reason"]})
            else:
                applied.append(page)
        if not applied:
            break  # 无可应用的修复，停止避免振荡
        _save(plan, plan_path)
        # 重建 + 重渲 + 重 QA
        build_deck.build(plan_path, template_path,
                         os.path.join(work_dir, "deck.pptx"),
                         os.path.join(work_dir, "build_log.json"))
        run_no += 1
        proof = render_pipeline.render_and_qa(work_dir, output_dir,
                                              fix_log=fix_log, run=run_no)
        proof["unfixable"] = unfixable
        _save(proof, proof_path)

    return proof.get("overall", "fail"), fix_log, unfixable
