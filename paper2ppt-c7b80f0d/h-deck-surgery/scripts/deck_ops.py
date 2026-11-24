#!/usr/bin/env python3
"""deck_ops.py — 幂等应用 ops_journal.json 到起始稿，自动版本快照与操作日志。

用法:
    python3 deck_ops.py <deck.pptx> --ops ops_journal.json --out deck_final.pptx \
        --versions-dir versions/ --log ops_log.json

幂等语义：
  * op_id 去重：--log 已存在时，已 applied 的 op_id 直接 skipped，不重复应用、不新增版本；
  * 内容级幂等：replace_text 的 old 不存在而 new 已存在 -> skipped(already applied)；
    set_title 目标值已相同 -> skipped(no-op)；
  * 上次 failed 的 op 会重试。
版本快照：首次运行先把原稿复制为 versions/v1.pptx，之后每成功应用 1 个 op 存 vN.pptx；
  change_records 的 rollback 指向前一版本文件。
退出码：0 = 全部 applied/skipped；2 = 有 failed；3 = python-pptx 缺失（无法编辑）。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_common as dc

if dc.HAS_PPTX:
    from pptx import Presentation
    from pptx.util import Inches

TEXT_OPS = {"set_title", "replace_text", "set_bullets", "add_figure"}
ALL_OPS = TEXT_OPS | {"insert_slide", "delete_slide", "move_slide", "set_notes"}


class OpError(Exception):
    pass


def _slide(prs, num: int):
    n = len(prs.slides._sldIdLst)
    if not (1 <= num <= n):
        raise OpError(f"slide {num} out of range (deck has {n} slides)")
    return prs.slides[num - 1]


def _title_shape(slide):
    shp = slide.shapes.title
    if shp is None:
        raise OpError("slide has no title placeholder")
    return shp


def _body_shape(slide, placeholder_idx=None):
    title = slide.shapes.title
    for shape in slide.shapes:
        if not shape.is_placeholder or not shape.has_text_frame:
            continue
        if title is not None and shape == title:
            continue
        if placeholder_idx is not None and shape.placeholder_format.idx != placeholder_idx:
            continue
        ph_type = str(shape.placeholder_format.type)
        if "TITLE" in ph_type:
            continue
        return shape
    # 非占位符文本框兜底
    for shape in slide.shapes:
        if shape.has_text_frame and shape is not title:
            return shape
    raise OpError("slide has no body placeholder/text frame")


def op_set_title(prs, op):
    slide = _slide(prs, op["slide"])
    new = op["params"]["title"]
    shp = _title_shape(slide)
    if (shp.text_frame.text or "") == new:
        return "skipped", "no-op: title already equals target"
    shp.text_frame.text = new
    return "applied", f"title set to {new!r}"


def op_replace_text(prs, op):
    slide = _slide(prs, op["slide"])
    old, new = op["params"]["old"], op["params"]["new"]
    hits = 0
    new_present = False
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            joined = "".join(r.text for r in para.runs)
            if new in joined:
                new_present = True
            if old and old in joined:
                para.runs[0].text = joined.replace(old, new)
                for r in para.runs[1:]:
                    r.text = ""
                hits += 1
                new_present = True
    if hits:
        return "applied", f"replaced {hits}x {old!r} -> {new!r}"
    if new_present:
        return "skipped", "already applied: old text absent, new text present"
    raise OpError(f"old text not found on slide: {old!r}")


def op_set_bullets(prs, op):
    slide = _slide(prs, op["slide"])
    bullets = op["params"]["bullets"]
    shp = _body_shape(slide, op["params"].get("placeholder_idx"))
    tf = shp.text_frame
    current = [p.text for p in tf.paragraphs if p.text.strip()]
    if current == list(bullets):
        return "skipped", "no-op: bullets already equal target"
    tf.clear()
    for i, b in enumerate(bullets):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.text = b
    return "applied", f"{len(bullets)} bullets set"


def op_insert_slide(prs, op):
    after = int(op.get("after", op["params"].get("after", 0)))
    params = op["params"]
    layout_name = params.get("layout", "Title and Content")
    layout = None
    for lay in prs.slide_layouts:
        if lay.name == layout_name:
            layout = lay
            break
    if layout is None:
        layout = prs.slide_layouts[min(1, len(prs.slide_layouts) - 1)]
    n = len(prs.slides._sldIdLst)
    if not (0 <= after <= n):
        raise OpError(f"after={after} out of range (deck has {n} slides)")
    slide = prs.slides.add_slide(layout)
    if params.get("title") and slide.shapes.title is not None:
        slide.shapes.title.text_frame.text = params["title"]
    if params.get("bullets"):
        try:
            shp = _body_shape(slide)
            tf = shp.text_frame
            tf.clear()
            for i, b in enumerate(params["bullets"]):
                para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                para.text = b
        except OpError:
            pass
    if params.get("notes"):
        slide.notes_slide.notes_text_frame.text = params["notes"]
    xml_slides = prs.slides._sldIdLst
    ids = list(xml_slides)
    xml_slides.remove(ids[-1])
    xml_slides.insert(after, ids[-1])
    return "applied", f"slide inserted at position {after + 1} (layout={layout.name!r})"


def op_delete_slide(prs, op):
    num = op["slide"]
    _slide(prs, num)
    xml_slides = prs.slides._sldIdLst
    slide_id = list(xml_slides)[num - 1]
    rId = slide_id.rId if hasattr(slide_id, "rId") else slide_id.get(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )
    prs.part.drop_rel(rId)
    xml_slides.remove(slide_id)
    return "applied", f"slide {num} deleted"


def op_move_slide(prs, op):
    frm, to = int(op["params"]["from"]), int(op["params"]["to"])
    n = len(prs.slides._sldIdLst)
    if not (1 <= frm <= n and 1 <= to <= n):
        raise OpError(f"move from={frm} to={to} out of range (deck has {n} slides)")
    xml_slides = prs.slides._sldIdLst
    ids = list(xml_slides)
    el = ids[frm - 1]
    xml_slides.remove(el)
    xml_slides.insert(to - 1, el)
    return "applied", f"slide moved {frm} -> {to}"


def op_set_notes(prs, op):
    slide = _slide(prs, op["slide"])
    notes = op["params"]["notes"]
    tf = slide.notes_slide.notes_text_frame
    if (tf.text or "") == notes:
        return "skipped", "no-op: notes already equal target"
    tf.text = notes
    return "applied", f"notes set ({len(notes)} chars)"


def op_add_figure(prs, op, base_dir):
    slide = _slide(prs, op["slide"])
    img = op["params"]["image"]
    if not os.path.isabs(img):
        img = os.path.join(base_dir, img)
    if not os.path.exists(img):
        raise OpError(f"image not found: {img}")
    left = Inches(float(op["params"].get("left_in", 1.0)))
    top = Inches(float(op["params"].get("top_in", 3.2)))
    width = Inches(float(op["params"].get("width_in", 5.0)))
    slide.shapes.add_picture(img, left, top, width=width)
    return "applied", f"figure added from {os.path.basename(img)}"


HANDLERS = {
    "set_title": op_set_title,
    "replace_text": op_replace_text,
    "set_bullets": op_set_bullets,
    "insert_slide": op_insert_slide,
    "delete_slide": op_delete_slide,
    "move_slide": op_move_slide,
    "set_notes": op_set_notes,
}


def _next_version(versions_dir: str) -> int:
    existing = [
        int(m.group(1))
        for f in os.listdir(versions_dir)
        if (m := re.fullmatch(r"v(\d+)\.pptx", f))
    ] if os.path.isdir(versions_dir) else []
    return (max(existing) + 1) if existing else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="幂等应用 ops_journal 到 pptx，自动快照 versions/vN.pptx")
    ap.add_argument("deck", help="起始稿 pptx")
    ap.add_argument("--ops", required=True, help="ops_journal.json")
    ap.add_argument("--out", required=True, help="最终 deck 输出路径")
    ap.add_argument("--versions-dir", required=True, help="版本快照目录")
    ap.add_argument("--log", required=True, help="ops_log.json（存在则幂等续跑）")
    args = ap.parse_args(argv)

    if not dc.HAS_PPTX:
        print("error: python-pptx not installed; deck editing unavailable "
              "(engine would be stdlib-fallback which is read-only)", file=sys.stderr)
        return 3
    for p in (args.deck, args.ops):
        if not os.path.exists(p):
            print(f"error: input not found: {p}", file=sys.stderr)
            return 2

    journal = dc.load_json(args.ops)
    ops = journal.get("ops", [])
    base_dir = os.path.dirname(os.path.abspath(args.ops))
    os.makedirs(args.versions_dir, exist_ok=True)

    if os.path.exists(args.log):
        log = dc.load_json(args.log)
    else:
        log = {"journal_id": journal.get("journal_id"), "base_deck": os.path.abspath(args.deck),
               "runs": [], "ops": []}
    done = {o["op_id"]: o for o in log["ops"] if o["status"] == "applied"}

    prs = Presentation(args.deck if not log["runs"] else _latest_version(args.versions_dir))
    if not log["runs"]:
        # 首次运行：v1 = 原稿快照
        shutil.copyfile(args.deck, os.path.join(args.versions_dir, "v1.pptx"))

    n_applied = n_skipped = n_failed = 0
    for op in ops:
        op_id = op.get("op_id")
        kind = op.get("op")
        if not op_id or kind not in ALL_OPS:
            rec = {"op_id": op_id or "?", "op": kind or "?", "slide": op.get("slide"),
                   "status": "failed", "detail": "missing op_id or unknown op type",
                   "version_after": None, "rollback": None, "reason": op.get("reason", "")}
            log["ops"].append(rec)
            n_failed += 1
            continue
        if op_id in done:
            n_skipped += 1
            print(f"  skipped {op_id} ({kind}): op_id already applied in a previous run")
            continue
        try:
            if kind == "add_figure":
                status, detail = op_add_figure(prs, op, base_dir)
            else:
                status, detail = HANDLERS[kind](prs, op)
        except (OpError, KeyError, IndexError) as e:
            status, detail = "failed", str(e)
        rec = {"op_id": op_id, "op": kind,
               "slide": op.get("slide", op.get("after")),
               "status": status, "detail": detail,
               "version_after": None, "rollback": None,
               "reason": op.get("reason", "")}
        if status == "applied":
            ver = _next_version(args.versions_dir)
            vpath = os.path.join(args.versions_dir, f"v{ver}.pptx")
            prs.save(vpath)
            rec["version_after"] = f"v{ver}"
            rec["rollback"] = os.path.abspath(
                os.path.join(args.versions_dir, f"v{ver - 1}.pptx")
            )
            n_applied += 1
        elif status == "skipped":
            n_skipped += 1
        else:
            n_failed += 1
        # 已存在记录（上次 failed）则更新，否则追加
        for i, old in enumerate(log["ops"]):
            if old["op_id"] == op_id:
                log["ops"][i] = rec
                break
        else:
            log["ops"].append(rec)
        print(f"  {status} {op_id} ({kind}): {detail}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    prs.save(args.out)
    log["runs"].append({"run": len(log["runs"]) + 1, "ops_in_journal": len(ops),
                        "applied": n_applied, "skipped": n_skipped, "failed": n_failed,
                        "out": os.path.abspath(args.out)})
    dc.dump_json(log, args.log)
    print(f"deck_ops done: applied={n_applied} skipped={n_skipped} failed={n_failed} "
          f"-> {args.out} (log: {args.log})")
    return 2 if n_failed else 0


def _latest_version(versions_dir: str) -> str:
    vers = [
        (int(m.group(1)), f)
        for f in os.listdir(versions_dir)
        if (m := re.fullmatch(r"v(\d+)\.pptx", f))
    ]
    if not vers:
        raise FileNotFoundError(f"no versions found in {versions_dir}; cannot resume")
    return os.path.join(versions_dir, max(vers)[1])


if __name__ == "__main__":
    sys.exit(main())
