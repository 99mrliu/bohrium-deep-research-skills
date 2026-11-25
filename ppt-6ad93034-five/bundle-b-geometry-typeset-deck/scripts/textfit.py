#!/usr/bin/env python3
"""textfit.py -- deterministic text measurement and overflow-resolving layout engine.

Importable (string_width_pt, wrap_text, build_layout) and CLI:

    textfit.py --plan work/plan.json --theme work/theme.json --out work/layout.json

Width model (see references/layout_engine.md): per-character advance factors in em,
summed and multiplied by the font size, plus a conservative +8% safety margin.
CJK ideographs / fullwidth punctuation 1.00em, ASCII lowercase 0.52em, ASCII
UPPERCASE 0.68em (caps are much wider), digits 0.55em, space 0.28em, narrow glyphs
(i l j t . , : ; ' ! |) 0.28em, wide (m w M W @ %) 0.85em, everything else 0.55em.
Calibrated against common sans fonts; intentionally conservative so that
PowerPoint/LibreOffice real metrics almost always come out narrower than the
prediction (never unreadably shrunk, never overlapping).

Title policy (before the body ladder): titles step down a font ladder
(28/24/20pt content, 30/26/22/18pt deck title) until they fit their line budget
(2 lines content, 3 deck title); the title-slide subtitle is stacked below the
RESOLVED title box, so multi-line titles cannot overlap body text.

Overflow policy ladder (per slide, in order):
  (a) reduce body font 18 -> 16 -> 14 pt (HARD FLOOR, never below 14);
  (b) split remaining bullets onto continuation slides "<title> (cont.)"
      inserted immediately after the source slide (max MAX_CONTINUATIONS);
  (c) still overflowing -> move the remainder to role:"backup" slides appended
      at the very end of the deck.
Every fired policy step is logged in actions[]; anomalies go to warnings[].
Output is a pure function of (plan, theme): identical input -> identical layout.json.
"""
import argparse
import json
import os
import sys
import unicodedata

EMU_PER_PT = 12700
SAFETY = 1.08  # +8% conservative safety margin on all width predictions

NARROW = set("iljt.,:;'!|")
WIDE = set("mwMW@%")

TITLE_SIZES_PT = [28.0, 24.0, 20.0]       # content-slide title ladder (<=2 lines)
DECKTITLE_SIZES_PT = [30.0, 26.0, 22.0, 18.0]  # role:"title" main title ladder
TITLE_MAX_LINES = 2         # content-slide titles may occupy at most 2 lines
DECKTITLE_MAX_LINES = 3     # deck title on the title slide may occupy 3
BODY_SIZES_PT = [18.0, 16.0, 14.0]  # policy ladder, 14pt hard floor
SOURCE_SIZE_PT = 10.5
FOOTER_SIZE_PT = 9.0
LINE_HEIGHT = 1.25          # multiple of font size
BULLET_GAP = 0.35           # extra gap between bullets, multiple of font size
BULLET_INDENT_PT = 16.0
MAX_CONTINUATIONS = 2       # policy step (b) budget per logical slide

MARGIN_X_PT = 48.0
TITLE_Y_PT = 20.0
TITLE_PAD_PT = 8.0
BODY_TOP_GAP_PT = 12.0
FOOTER_ZONE_FRAC = 0.06     # bottom 6% of slide reserved for footer/slide-no
IMAGE_WIDTH_FRAC = 0.40     # right-hand image column when slide has an image


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------
def char_factor(ch):
    """Advance width of one character, in em."""
    if ch == " ":
        return 0.28
    o = ord(ch)
    if o < 128:
        if ch.isdigit():
            return 0.55
        if ch in NARROW:
            return 0.28
        if ch in WIDE:
            return 0.85
        if ch.isalpha():
            return 0.68 if ch.isupper() else 0.52
        return 0.55
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 1.00  # CJK ideographs and fullwidth punctuation
    return 0.55


def string_width_pt(s, size_pt):
    """Predicted rendered width of string `s` at `size_pt`, in points."""
    return sum(char_factor(c) for c in s) * size_pt * SAFETY


def _tokens(text):
    """Split into wrappable tokens: latin words, single CJK/fullwidth chars, spaces."""
    toks, cur = [], ""
    for ch in text:
        wide = ord(ch) >= 128 and unicodedata.east_asian_width(ch) in ("W", "F")
        if wide:
            if cur:
                toks.append(cur)
                cur = ""
            toks.append(ch)
        elif ch == " ":
            if cur:
                toks.append(cur)
                cur = ""
            toks.append(" ")
        else:
            cur += ch
    if cur:
        toks.append(cur)
    return toks


def wrap_text(text, box_w_pt, size_pt):
    """Greedy wrap of `text` to `box_w_pt` at `size_pt`. Returns list of lines.

    Breaks at spaces for latin runs, anywhere for CJK. A single token wider
    than the box is hard-split character by character. Deterministic.
    """
    text = (text or "").strip()
    if not text:
        return []
    lines, cur = [], ""
    for tok in _tokens(text):
        if tok == " ":
            cand = cur + " " if cur else ""
            if cand and string_width_pt(cand, size_pt) <= box_w_pt:
                cur = cand
            continue
        cand = cur + tok
        if not cur or string_width_pt(cand, size_pt) <= box_w_pt:
            cur = cand
            continue
        # token does not fit on current line
        if cur:
            lines.append(cur.rstrip())
            cur = ""
        if string_width_pt(tok, size_pt) <= box_w_pt:
            cur = tok
            continue
        # hard-split an overlong token
        for ch in tok:
            if cur and string_width_pt(cur + ch, size_pt) > box_w_pt:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------
def _geometry(theme):
    w_pt = theme["slide_w_emu"] / EMU_PER_PT
    h_pt = theme["slide_h_emu"] / EMU_PER_PT
    footer_h = h_pt * FOOTER_ZONE_FRAC
    return {
        "w_pt": w_pt, "h_pt": h_pt,
        "margin_x": MARGIN_X_PT,
        "footer_h": footer_h,
    }


def _box(x, y, w, h):
    """pt box -> EMU box dict."""
    return {"x": round(x * EMU_PER_PT), "y": round(y * EMU_PER_PT),
            "w": round(w * EMU_PER_PT), "h": round(h * EMU_PER_PT)}


def _bullets_height(bullets, size_pt, text_w_pt):
    """Total rendered height (pt) of wrapped bullets; also returns wrapped lines."""
    wrapped = []
    total = 0.0
    line_h = size_pt * LINE_HEIGHT
    gap = size_pt * BULLET_GAP
    for b in bullets:
        lines = wrap_text(b, text_w_pt, size_pt) or [""]
        wrapped.append(lines)
        total += len(lines) * line_h + gap
    if wrapped:
        total -= gap
    return total, wrapped


def _fit_bullets(bullets, size_pt, text_w_pt, box_h_pt):
    """Split bullets into pages that each fit box_h_pt at size_pt.

    Returns (pages, wrapped_all): pages = list of bullet-index lists.
    A single bullet taller than the whole box still gets its own page
    (logged by caller as a warning; never shrunk below the floor).
    """
    line_h = size_pt * LINE_HEIGHT
    gap = size_pt * BULLET_GAP
    pages, cur, used = [], [], 0.0
    wrapped_all = []
    for idx, b in enumerate(bullets):
        lines = wrap_text(b, text_w_pt, size_pt) or [""]
        wrapped_all.append(lines)
        need = len(lines) * line_h + (gap if cur else 0.0)
        if cur and used + need > box_h_pt:
            pages.append(cur)
            cur, used = [], 0.0
            need = len(lines) * line_h
        cur.append(idx)
        used += need
    if cur:
        pages.append(cur)
    return pages, wrapped_all


# --------------------------------------------------------------------------
# layout builder
# --------------------------------------------------------------------------
def build_layout(plan, theme):
    """Resolve plan.json + theme.json into concrete per-slide geometry."""
    g = _geometry(theme)
    w_pt, h_pt, mx = g["w_pt"], g["h_pt"], g["margin_x"]
    content_w = w_pt - 2 * mx
    out_slides, actions, warnings = [], [], []
    backup_queue = []   # (origin_id, origin_title, bullets, size_pt)

    for sidx, slide in enumerate(plan.get("slides", [])):
        sid = slide.get("id", "s%d" % (sidx + 1))
        role = slide.get("role", "content")
        title = slide.get("title", "")
        bullets = list(slide.get("bullets", []))
        notes = slide.get("notes", "")
        source_line = slide.get("source_line")
        image = slide.get("image")

        # --- title box: shrink ladder, then bounded multi-line --------------
        if role == "title":
            ladder, max_lines = DECKTITLE_SIZES_PT, DECKTITLE_MAX_LINES
        else:
            ladder, max_lines = TITLE_SIZES_PT, TITLE_MAX_LINES
        t_size, t_lines = ladder[-1], [""]
        for cand in ladder:
            cand_lines = wrap_text(title, content_w, cand) or [""]
            t_size, t_lines = cand, cand_lines
            if len(cand_lines) <= max_lines:
                break
        if len(t_lines) > 1:
            actions.append(
                "slide %s: title fit -> %.0fpt x %d line(s)"
                % (sid, t_size, len(t_lines)))
        if len(t_lines) > max_lines:
            warnings.append(
                "slide %s: title still %d lines at %.0fpt floor: %r"
                % (sid, len(t_lines), t_size, title))
        title_h = max(1, len(t_lines)) * t_size * LINE_HEIGHT + TITLE_PAD_PT
        title_box = dict(_box(mx, TITLE_Y_PT, content_w, title_h),
                         size_pt=t_size, lines=t_lines)

        body_y = TITLE_Y_PT + title_h + BODY_TOP_GAP_PT
        # --- source line reservation ---------------------------------------
        source_box = None
        if source_line:
            s_lines = wrap_text(source_line, content_w, SOURCE_SIZE_PT) or [""]
            s_h = len(s_lines) * SOURCE_SIZE_PT * LINE_HEIGHT + 4
            source_box = dict(_box(mx, h_pt - g["footer_h"] - s_h - 4,
                                   content_w, s_h),
                              size_pt=SOURCE_SIZE_PT, lines=s_lines)
        body_bottom = h_pt - g["footer_h"] - 6
        if source_box:
            body_bottom = source_box["y"] / EMU_PER_PT - 6
        body_h = body_bottom - body_y

        # --- image column reservation --------------------------------------
        body_w = content_w
        image_box = None
        if image:
            img_w = content_w * IMAGE_WIDTH_FRAC
            body_w = content_w - img_w - 18
            image_box = _box(mx + body_w + 18, body_y, img_w, body_h * 0.62)

        # --- body fitting: policy ladder ------------------------------------
        text_w = body_w - BULLET_INDENT_PT
        chosen_size, pages, wrapped = None, None, None
        if role == "title":
            # title slides: bullets are a subtitle block, single page, no split
            for size in BODY_SIZES_PT:
                need, wr = _bullets_height(bullets, size, content_w - BULLET_INDENT_PT)
                if need <= body_h or size == BODY_SIZES_PT[-1]:
                    chosen_size, pages, wrapped = size, [list(range(len(bullets)))], wr
                    break
            # adaptive vertical stack: subtitle starts only BELOW the resolved
            # title box, so a multi-line deck title can never overlap it
            title_y = h_pt * 0.22
            body_y = title_y + title_h + 0.05 * h_pt
            title_box = dict(_box(mx, title_y, content_w, title_h),
                             size_pt=t_size, lines=t_lines)
            body_h = body_bottom - body_y
            if body_h < 60:
                warnings.append(
                    "slide %s: title consumes most of the title slide; "
                    "subtitle area only %.0fpt" % (sid, body_h))
        else:
            for size in BODY_SIZES_PT:
                need, wr = _bullets_height(bullets, size, text_w)
                if need <= body_h:
                    chosen_size, pages, wrapped = size, [list(range(len(bullets)))], wr
                    if size != BODY_SIZES_PT[0]:
                        actions.append({
                            "slide": sid, "action": "shrink_font",
                            "detail": "body font reduced %.0f->%.0fpt to fit (policy a)"
                                      % (BODY_SIZES_PT[0], size)})
                    break
            if chosen_size is None:
                # policy (b): split at the 14pt floor
                chosen_size = BODY_SIZES_PT[-1]
                pages, wrapped = _fit_bullets(bullets, chosen_size, text_w, body_h)
                actions.append({
                    "slide": sid, "action": "shrink_font",
                    "detail": "body font at 14pt floor and still overflowing "
                              "(policy a exhausted)"})
                if len(pages) > 1:
                    n_cont = min(len(pages) - 1, MAX_CONTINUATIONS)
                    actions.append({
                        "slide": sid, "action": "split_continuation",
                        "detail": "%d bullets over %d pages at 14pt; emitting %d "
                                  "continuation slide(s) (policy b)"
                                  % (len(bullets), len(pages), n_cont)})
                if len(pages) - 1 > MAX_CONTINUATIONS:
                    rest = [i for pg in pages[MAX_CONTINUATIONS + 1:] for i in pg]
                    backup_queue.append((sid, title, [bullets[i] for i in rest],
                                         chosen_size, text_w, body_h))
                    pages = pages[:MAX_CONTINUATIONS + 1]
                    actions.append({
                        "slide": sid, "action": "move_to_backup",
                        "detail": "%d bullets exceed continuation budget; moved "
                                  "to backup slides at deck end (policy c)"
                                  % len(rest)})
        if chosen_size is None:  # no bullets at all
            chosen_size = BODY_SIZES_PT[0]
            pages, wrapped = [[]], []

        # --- emit the slide + continuation slides ---------------------------
        def _emit(sid_, role_, title_, page_idx_list, cont_idx):
            items = []
            for i in page_idx_list:
                items.append({"text": bullets[i], "lines": wrapped[i], "bullet": True})
            body_box = dict(_box(mx, body_y, body_w, body_h),
                            size_pt=chosen_size, items=items)
            if cont_idx > 0:
                title_ = "%s (cont.)" % title_
                tl = wrap_text(title_, content_w, t_size) or [""]
                tbox = dict(_box(mx, TITLE_Y_PT, content_w, title_h),
                            size_pt=t_size, lines=tl)
            else:
                tbox = title_box
            return {
                "id": sid_ if cont_idx == 0 else "%s-c%d" % (sid_, cont_idx),
                "role": role_, "title": title_,
                "title_box": tbox, "body_box": body_box,
                "source_box": source_box if cont_idx == 0 else None,
                "image": image if cont_idx == 0 else None,
                "image_box": image_box if cont_idx == 0 else None,
                "notes": notes if cont_idx == 0 else "",
                "footer": plan.get("meta", {}).get("title", ""),
            }

        for pno, page in enumerate(pages):
            out_slides.append(_emit(sid, role, title, page, pno))

    # --- policy (c): backup slides ------------------------------------------
    for origin_id, origin_title, rest, size_pt, _tw, _bh in backup_queue:
        # resolve the backup title (worst-case "(cont.)" suffix) BEFORE fixing
        # the body top, so a 2-line backup title can never overlap the body
        t_worst = "Backup — overflow from %s (cont.)" % origin_id
        bt_size, bt_lines = TITLE_SIZES_PT[-1], [t_worst]
        for cand in TITLE_SIZES_PT:
            bt_lines = wrap_text(t_worst, w_pt - 2 * mx, cand) or [t_worst]
            bt_size = cand
            if len(bt_lines) <= TITLE_MAX_LINES:
                break
        bt_h = max(1, len(bt_lines)) * bt_size * LINE_HEIGHT + TITLE_PAD_PT
        body_y = TITLE_Y_PT + bt_h + BODY_TOP_GAP_PT
        body_bottom = h_pt - g["footer_h"] - 6
        body_h = body_bottom - body_y
        pages, wrapped_all = _fit_bullets(rest, size_pt,
                                          (w_pt - 2 * mx) - BULLET_INDENT_PT, body_h)
        for pno, page in enumerate(pages):
            suffix = "" if pno == 0 else " (cont.)"
            items = [{"text": rest[i], "lines": wrapped_all[i], "bullet": True}
                     for i in page]
            t = "Backup — overflow from %s%s" % (origin_id, suffix)
            out_slides.append({
                "id": "%s-b%d" % (origin_id, pno + 1),
                "role": "backup", "title": t,
                "title_box": dict(_box(mx, TITLE_Y_PT, w_pt - 2 * mx, bt_h),
                                  size_pt=bt_size,
                                  lines=wrap_text(t, w_pt - 2 * mx, bt_size)),
                "body_box": dict(_box(mx, body_y, w_pt - 2 * mx, body_h),
                                 size_pt=size_pt, items=items),
                "source_box": None, "image": None, "image_box": None,
                "notes": "Overflow bullets moved from slide %s (policy c)." % origin_id,
                "footer": plan.get("meta", {}).get("title", ""),
            })
        actions.append({
            "slide": origin_id, "action": "backup_slides_emitted",
            "detail": "%d backup slide(s) appended at deck end for overflow from %r"
                      % (len(pages), origin_title)})

    for n, s in enumerate(out_slides, start=1):
        s["slide_no"] = n

    return {
        "meta": dict(plan.get("meta", {})),
        "slide_w_emu": theme["slide_w_emu"],
        "slide_h_emu": theme["slide_h_emu"],
        "fonts": theme.get("fonts", {}),
        "colors": theme.get("colors", {}),
        "slides": out_slides,
        "actions": actions,
        "warnings": warnings,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic text-fit layout resolver.")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--theme", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    with open(args.theme, encoding="utf-8") as fh:
        theme = json.load(fh)
    layout = build_layout(plan, theme)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(layout, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    n_cont = sum(1 for s in layout["slides"] if "(cont.)" in s["title"])
    print("textfit: %d slide(s) (%d continuation, %d backup); %d action(s), "
          "%d warning(s) -> %s"
          % (len(layout["slides"]), n_cont,
             sum(1 for s in layout["slides"] if s["role"] == "backup"),
             len(layout["actions"]), len(layout["warnings"]), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
