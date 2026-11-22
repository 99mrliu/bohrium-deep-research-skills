#!/usr/bin/env python3
"""survey.py — Step 1 of contract-gate-slides.

Scan the runtime input directory, normalize case.json / material.json /
artifacts/slide-workorder.json into a single case brief, and compile a
machine-checkable requirement list (the "contract gate" items).

Never raises: every missing or malformed input is recorded as an assumption.
Outputs:
  $WORK/case_brief.json    normalized case facts + assumptions
  $WORK/requirements.json  [{id, kind, desc, source}] gate items
Env: CASE_INPUT_DIR (default /input), CASE_WORK_DIR (default /app/work),
     CASE_OUTPUT_DIR (default /app/output)
"""
import json, os, re, sys, glob

IN = os.environ.get("CASE_INPUT_DIR", "/input")
WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def jload(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def first(*vals):
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None


def main():
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    assumptions = []

    case = jload(os.path.join(IN, "case.json")) or {}
    material = jload(os.path.join(IN, "material.json")) or {}
    wo = jload(os.path.join(IN, "artifacts", "slide-workorder.json"))
    if wo is None:
        # tolerate workorder at other locations
        for cand in glob.glob(os.path.join(IN, "**", "*workorder*.json"), recursive=True):
            wo = jload(cand)
            if wo:
                assumptions.append(f"workorder 取自非常规路径 {cand}")
                break
    wo = wo or {}
    if not case:
        assumptions.append("缺少 case.json，字段由 workorder/material 推断")
    if not wo:
        assumptions.append("缺少 slide-workorder.json，采用默认约束（12 页/15 分钟/评审受众）")

    pdfs = sorted(glob.glob(os.path.join(IN, "**", "*.pdf"), recursive=True))
    pptxs = sorted(glob.glob(os.path.join(IN, "**", "*.pptx"), recursive=True))
    template = next((p for p in pptxs if "target" in os.path.basename(p).lower()
                     or "template" in os.path.basename(p).lower()), None)
    starting = next((p for p in pptxs if "start" in os.path.basename(p).lower()
                     or "starting" in os.path.basename(p).lower()), None)
    if template is None and pptxs:
        others = [p for p in pptxs if p != starting]
        if others:
            template = others[0]
            assumptions.append(f"未找到 target-template.pptx，以 {os.path.basename(template)} 为模板")
    if not pdfs:
        assumptions.append("未找到论文 PDF：证据锚定检查将无法运行，需在 result.json 记为 partial")
    if template is None:
        assumptions.append("未找到模板 PPTX：将以 python-pptx 默认空白模板成稿，并在 exceptions 声明")

    explicit_mode = first(wo.get("mode"), case.get("mode"))
    mode = str(explicit_mode or ("edit" if starting else "create")).lower()
    if explicit_mode is None and starting:
        assumptions.append("未显式给出 mode，检测到 starting-deck.pptx，判定为 edit")

    brief = {
        "case_id": first(case.get("case_id"), case.get("id"), wo.get("case_id"), "UNKNOWN-CASE"),
        "mode": mode,
        "audience": first(wo.get("audience"), case.get("audience"), "评审专家"),
        "time_minutes": first(wo.get("time_minutes"), case.get("time_minutes"), 15),
        "slide_count": int(first(wo.get("total_slides"), wo.get("slide_count"),
                                 case.get("slide_count"), 12)),
        "language": str(first(wo.get("language"), case.get("language"), "zh")),
        "notes_required": bool(first(wo.get("notes_required"), True)),
        "source_line_required": bool(first(wo.get("source_line_required"), True)),
        "required_roles": first(wo.get("required_roles"),
                                ["title", "background", "method", "result", "conclusion"]),
        "paper_pdf": pdfs[0] if pdfs else None,
        "extra_pdfs": pdfs[1:],
        "template_pptx": template,
        "starting_deck_pptx": starting,
        "material_title": first(material.get("title"), ""),
        "assumptions": assumptions,
    }
    with open(os.path.join(WORK, "case_brief.json"), "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)

    # --- compile the contract gate list -----------------------------------
    reqs = [
        {"id": "G01-deck-editable", "kind": "artifact",
         "desc": "交付原生可编辑 presentation.pptx（python-pptx 生成，非图片拼版）", "source": "output_contract.editable_source"},
        {"id": "G02-slide-count", "kind": "structure",
         "desc": f"总页数 == {brief['slide_count']}", "source": "slide-workorder"},
        {"id": "G03-roles", "kind": "structure",
         "desc": "覆盖必需叙事角色: " + "/".join(brief["required_roles"]), "source": "slide-workorder"},
        {"id": "G04-notes", "kind": "content",
         "desc": "每页含演讲备注（讲稿）", "source": "slide-workorder"},
        {"id": "G05-source-line", "kind": "content",
         "desc": "每页含来源行（论文页码/图表号）", "source": "slide-workorder"},
        {"id": "G06-anchor-numbers", "kind": "evidence",
         "desc": "幻灯片中的数字必须命中所锚定论文页文本（禁止按印象取整）", "source": "rubric.结果正确性"},
        {"id": "G07-figure-real", "kind": "evidence",
         "desc": "插图一律来自论文 PDF 真实裁剪，禁止占位图/凭空曲线", "source": "rubric.结果正确性"},
        {"id": "G08-template-inherit", "kind": "template",
         "desc": "母版/版式/主题与模板字节级一致；无 run 级字体名覆盖", "source": "rubric.模板约束"},
        {"id": "G09-export-pdf", "kind": "artifact",
         "desc": "导出 PDF 且页数与 pptx 一致；每页 PNG 预览", "source": "output_contract.export_artifact"},
        {"id": "G10-content-map", "kind": "artifact",
         "desc": "result.json 的 content_map 覆盖每一页且锚点齐全", "source": "output_contract.content_map"},
        {"id": "G11-result-fields", "kind": "artifact",
         "desc": "result.json 含 case_id/status/editable_source/export_artifact/content_map/compliance_checks/exceptions",
         "source": "output_contract"},
        {"id": "G12-density", "kind": "content",
         "desc": "每页 ≤6 条 bullet；每条 ≤60 个中文字符或 90 个拉丁字符", "source": "rubric.页面密度"},
    ]
    with open(os.path.join(WORK, "requirements.json"), "w", encoding="utf-8") as f:
        json.dump(reqs, f, ensure_ascii=False, indent=2)

    print(json.dumps({"case_id": brief["case_id"], "mode": brief["mode"],
                      "slide_count": brief["slide_count"], "audience": brief["audience"],
                      "paper": bool(brief["paper_pdf"]), "template": bool(brief["template_pptx"]),
                      "requirements": len(reqs), "assumptions": assumptions},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
