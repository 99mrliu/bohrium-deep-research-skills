#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_qa.py —— 导出 PDF 渲染取证门（R1–R5）。

仅依赖 Python3 标准库 + 外部工具 pdftotext / pdftoppm（poppler）。
对一份"导出的 PDF"执行五条机器可判定的取证检查：

  R1  页数一致：实际页数必须等于 expectations.json 的 page_count。
  R2  空白页：某页 pdftotext 词数为 0 且整页墨水覆盖率 < blank_ink_threshold。
  R3  文字越界：pdftotext -bbox 词框超出页面矩形（容差 eps_pt），
      或词框下缘侵入页脚区（页面底部 footer_zone_fraction 比例）。
  R4  过小文字：某页词框高度中位数 < min_text_height_pt
      （导出后字体缩水 / 缩放链出错的信号；词数过少的页跳过）。
  R5  缺图：expected_figure_pages 中列出的页，其内容区
      （去掉页边距与页脚区）墨水覆盖率 < figure_ink_threshold。

用法：
  python3 render_qa.py DECK.pdf EXPECTATIONS.json [-o render_report.json]

退出码：
  0  全部通过
  1  存在违例（stdout 逐行打印 "CODE: detail"）
  2  用法 / IO / 工具缺失错误（pdftotext 或 pdftoppm 不在 PATH 上等）

所有判定为确定性：同一 PDF + 同一 expectations 重复运行结果一致。
"""

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

DEFAULTS = {
    "footer_zone_fraction": 0.08,
    "min_text_height_pt": 10.0,
    "expected_figure_pages": [],
    "blank_ink_threshold": 0.001,
    "figure_ink_threshold": 0.02,
    "content_margin_fraction": 0.05,
    "ink_pixel_threshold": 240,
    "render_dpi": 72,
    "eps_pt": 0.5,
    "min_words_for_height_check": 3,
}

XHTML_NS = "{http://www.w3.org/1999/xhtml}"


class UsageError(Exception):
    """用法 / IO / 工具错误 → exit 2。"""


# ---------------------------------------------------------------- 工具层

def require_tool(name):
    path = shutil.which(name)
    if not path:
        raise UsageError(
            "缺少外部工具 {}：render_qa 需要 poppler 的 pdftotext/pdftoppm 在 PATH 上；"
            "当前环境无法执行渲染取证，请安装 poppler 或如实记录降级（exit 2）。".format(name))
    return path


def run_tool(argv, label):
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise UsageError("无法执行 {}：{}".format(label, exc))
    if proc.returncode != 0:
        raise UsageError("{} 执行失败（exit {}）：{}".format(
            label, proc.returncode, proc.stderr.decode("utf-8", "replace")[:400]))
    return proc.stdout


def load_expectations(path):
    if not os.path.isfile(path):
        raise UsageError("expectations.json 不存在：{}".format(path))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UsageError("expectations.json 读取或解析失败：{}".format(exc))
    if not isinstance(raw, dict):
        raise UsageError("expectations.json 顶层必须是对象")
    exp = dict(DEFAULTS)
    exp.update(raw)
    for key in ("footer_zone_fraction", "blank_ink_threshold", "figure_ink_threshold",
                "content_margin_fraction"):
        v = exp[key]
        if not isinstance(v, (int, float)) or not (0 <= v < 1):
            raise UsageError("expectations 字段 {} 必须是 [0,1) 区间数值，得到 {!r}".format(key, v))
    if not isinstance(exp.get("page_count"), int) or exp["page_count"] < 1:
        raise UsageError("expectations 字段 page_count 必须是正整数（R1 需要它）")
    if not isinstance(exp["expected_figure_pages"], list) or \
            not all(isinstance(p, int) and p >= 1 for p in exp["expected_figure_pages"]):
        raise UsageError("expected_figure_pages 必须是正整数页码数组（1-based）")
    return exp


# ------------------------------------------------------- pdftotext -bbox

def parse_bbox(pdf_path, pdftotext):
    """返回 pages: [{width, height, words:[{xmin,ymin,xmax,ymax,text}]}]。"""
    xml_bytes = run_tool([pdftotext, "-bbox", pdf_path, "-"], "pdftotext -bbox")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise UsageError("pdftotext -bbox 输出解析失败：{}".format(exc))
    pages = []
    for page_el in root.iter(XHTML_NS + "page"):
        try:
            width = float(page_el.get("width"))
            height = float(page_el.get("height"))
        except (TypeError, ValueError):
            raise UsageError("pdftotext -bbox 输出缺页面尺寸属性")
        words = []
        for w_el in page_el.iter(XHTML_NS + "word"):
            try:
                box = {k: float(w_el.get(k)) for k in ("xMin", "yMin", "xMax", "yMax")}
            except (TypeError, ValueError):
                continue
            text = (w_el.text or "").strip()
            if text:
                words.append({
                    "xmin": box["xMin"], "ymin": box["yMin"],
                    "xmax": box["xMax"], "ymax": box["yMax"],
                    "text": text,
                })
        pages.append({"width": width, "height": height, "words": words})
    if not pages:
        raise UsageError("pdftotext -bbox 未返回任何页面，PDF 可能损坏：{}".format(pdf_path))
    return pages


# ------------------------------------------------- pdftoppm + 纯 Python PPM

def _ppm_token(data, idx):
    n = len(data)
    while idx < n:
        b = data[idx:idx + 1]
        if b.isspace():
            idx += 1
        elif b == b"#":
            while idx < n and data[idx] != 10:
                idx += 1
        else:
            break
    start = idx
    while idx < n and not data[idx:idx + 1].isspace():
        idx += 1
    return data[start:idx], idx


def ppm_ink_coverage(path, pixel_threshold, content_box=None):
    """解析 P6 PPM，返回 (整页墨水覆盖率, 内容区墨水覆盖率)。

    content_box = (row0, row1, col0, col1) 像素区间；None 时内容区=整页。
    墨水像素：RGB 均值 < pixel_threshold。
    """
    with open(path, "rb") as fh:
        data = fh.read()
    magic, idx = _ppm_token(data, 0)
    if magic != b"P6":
        raise UsageError("非 P6 PPM 文件：{}（magic={!r}）".format(path, magic))
    w_tok, idx = _ppm_token(data, idx)
    h_tok, idx = _ppm_token(data, idx)
    max_tok, idx = _ppm_token(data, idx)
    try:
        width, height, maxval = int(w_tok), int(h_tok), int(max_tok)
    except ValueError:
        raise UsageError("PPM 头损坏：{}".format(path))
    if maxval > 255:
        raise UsageError("暂不支持 maxval>255 的 PPM：{}".format(path))
    idx += 1  # 单个空白分隔符
    pixels = data[idx:idx + 3 * width * height]
    if len(pixels) < 3 * width * height:
        raise UsageError("PPM 像素数据截断：{}".format(path))

    if content_box is None:
        content_box = (0, height, 0, width)
    r0, r1, c0, c1 = content_box
    r0 = max(0, min(height, r0)); r1 = max(r0, min(height, r1))
    c0 = max(0, min(width, c0));  c1 = max(c0, min(width, c1))

    total_ink = 0
    content_ink = 0
    thr3 = 3 * pixel_threshold
    for row in range(height):
        base = row * width * 3
        in_rows = r0 <= row < r1
        for col in range(width):
            i = base + col * 3
            if pixels[i] + pixels[i + 1] + pixels[i + 2] < thr3:
                total_ink += 1
                if in_rows and c0 <= col < c1:
                    content_ink += 1
    total_px = width * height
    content_px = max(1, (r1 - r0) * (c1 - c0))
    return total_ink / total_px, content_ink / content_px


def render_pages(pdf_path, pdftoppm, dpi, workdir):
    """渲染全部页，返回按页码排序的 ppm 路径列表（1-based 下标即页码-1）。"""
    prefix = os.path.join(workdir, "page")
    run_tool([pdftoppm, "-r", str(dpi), pdf_path, prefix], "pdftoppm")
    names = [n for n in os.listdir(workdir)
             if re.fullmatch(r"page-\d+\.ppm", n)]
    if not names:
        raise UsageError("pdftoppm 未产出任何 PPM，PDF 可能损坏：{}".format(pdf_path))
    names.sort(key=lambda n: int(re.search(r"(\d+)", n).group(1)))
    return [os.path.join(workdir, n) for n in names]


# ---------------------------------------------------------------- 门控层

def gate_r1(actual_pages, exp, violations):
    expected = exp["page_count"]
    if actual_pages != expected:
        violations.append({
            "code": "R1", "page": None,
            "detail": "页数不一致：期望 {} 页，实际导出 {} 页".format(expected, actual_pages),
        })
        return False, "期望 {} 页，实际 {} 页".format(expected, actual_pages)
    return True, "页数一致（{} 页）".format(actual_pages)


def gate_r2(page_stats, exp, violations):
    checked = 0
    for st in page_stats:
        if st["word_count"] == 0 and st["ink_coverage"] < exp["blank_ink_threshold"]:
            violations.append({
                "code": "R2", "page": st["page"],
                "detail": "第 {} 页为空白页：无文本且整页墨水覆盖率 {:.5f} < 阈值 {:.5f}".format(
                    st["page"], st["ink_coverage"], exp["blank_ink_threshold"]),
            })
            checked += 1
    if checked:
        return False, "发现 {} 个空白页".format(checked)
    return True, "无空白页"


def gate_r3(pages, exp, violations):
    eps = exp["eps_pt"]
    bad = 0
    for pno, page in enumerate(pages, start=1):
        width, height = page["width"], page["height"]
        footer_top = height * (1.0 - exp["footer_zone_fraction"])
        for w in page["words"]:
            if (w["xmin"] < -eps or w["ymin"] < -eps or
                    w["xmax"] > width + eps or w["ymax"] > height + eps):
                bad += 1
                violations.append({
                    "code": "R3", "page": pno,
                    "detail": "第 {} 页词 {!r} 越界：bbox=({:.1f},{:.1f},{:.1f},{:.1f}) "
                              "超出页面矩形 ({:.0f}x{:.0f})".format(
                                  pno, w["text"], w["xmin"], w["ymin"], w["xmax"], w["ymax"],
                                  width, height),
                })
            elif w["ymax"] > footer_top:
                bad += 1
                violations.append({
                    "code": "R3", "page": pno,
                    "detail": "第 {} 页词 {!r} 侵入页脚区：yMax={:.1f} > 页脚区上缘 {:.1f} "
                              "(页面高 {:.0f}, 页脚比例 {:.2f})".format(
                                  pno, w["text"], w["ymax"], footer_top,
                                  height, exp["footer_zone_fraction"]),
                })
    if bad:
        return False, "发现 {} 处文字越界/页脚侵入".format(bad)
    return True, "全部词框在页面矩形内且未侵入页脚区"


def gate_r4(page_stats, exp, violations):
    min_h = exp["min_text_height_pt"]
    min_words = exp["min_words_for_height_check"]
    bad = 0
    for st in page_stats:
        if st["word_count"] < min_words:
            continue
        if st["median_word_height_pt"] < min_h:
            bad += 1
            violations.append({
                "code": "R4", "page": st["page"],
                "detail": "第 {} 页文字过小：词框高度中位数 {:.2f}pt < 阈值 {:.2f}pt "
                          "（{} 个词）".format(st["page"], st["median_word_height_pt"],
                                             min_h, st["word_count"]),
            })
    if bad:
        return False, "发现 {} 页文字过小".format(bad)
    return True, "各页词框高度中位数均达标"


def gate_r5(page_stats, exp, violations):
    bad = 0
    stats_by_page = {st["page"]: st for st in page_stats}
    actual = len(page_stats)
    for pno in exp["expected_figure_pages"]:
        st = stats_by_page.get(pno)
        if st is None:
            bad += 1
            violations.append({
                "code": "R5", "page": pno,
                "detail": "期望的图页第 {} 页不存在（实际仅 {} 页）".format(pno, actual),
            })
        elif st["content_ink_coverage"] < exp["figure_ink_threshold"]:
            bad += 1
            violations.append({
                "code": "R5", "page": pno,
                "detail": "第 {} 页应为图页但内容区墨水覆盖率 {:.5f} < 阈值 {:.5f}"
                          "（图可能丢失或被裁掉）".format(
                              pno, st["content_ink_coverage"], exp["figure_ink_threshold"]),
            })
    if bad:
        return False, "发现 {} 个图页异常".format(bad)
    return True, "全部期望图页内容区墨水达标"


# ---------------------------------------------------------------- 主流程

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="导出 PDF 渲染取证门（R1 页数 / R2 空白页 / R3 文字越界 / "
                    "R4 过小文字 / R5 缺图）")
    parser.add_argument("pdf", help="待检查的导出 PDF")
    parser.add_argument("expectations", help="expectations.json 路径")
    parser.add_argument("-o", "--output", default=None,
                        help="render_report.json 输出路径（默认 <pdf去掉扩展名>_render_report.json）")
    args = parser.parse_args(argv)

    try:
        if not os.path.isfile(args.pdf):
            raise UsageError("PDF 不存在：{}".format(args.pdf))
        pdftotext = require_tool("pdftotext")
        pdftoppm = require_tool("pdftoppm")
        exp = load_expectations(args.expectations)

        pages = parse_bbox(args.pdf, pdftotext)

        with tempfile.TemporaryDirectory(prefix="render_qa_") as workdir:
            ppm_paths = render_pages(args.pdf, pdftoppm, exp["render_dpi"], workdir)
            if len(ppm_paths) != len(pages):
                raise UsageError(
                    "pdftotext 报告 {} 页而 pdftoppm 渲染出 {} 页，工具链结果不一致".format(
                        len(pages), len(ppm_paths)))
            page_stats = []
            dpi = exp["render_dpi"]
            margin = exp["content_margin_fraction"]
            footer = exp["footer_zone_fraction"]
            for pno, (page, ppm) in enumerate(zip(pages, ppm_paths), start=1):
                # 页面尺寸(pt) → 像素
                px_w = round(page["width"] / 72.0 * dpi)
                px_h = round(page["height"] / 72.0 * dpi)
                content_box = (
                    round(px_h * margin), round(px_h * (1.0 - footer)),
                    round(px_w * margin), round(px_w * (1.0 - margin)),
                )
                ink, content_ink = ppm_ink_coverage(
                    ppm, exp["ink_pixel_threshold"], content_box)
                heights = [w["ymax"] - w["ymin"] for w in page["words"]]
                page_stats.append({
                    "page": pno,
                    "width_pt": page["width"],
                    "height_pt": page["height"],
                    "word_count": len(page["words"]),
                    "median_word_height_pt": (
                        round(statistics.median(heights), 3) if heights else None),
                    "ink_coverage": round(ink, 6),
                    "content_ink_coverage": round(content_ink, 6),
                })

        violations = []
        gates = {}
        gates["R1"] = gate_r1(len(pages), exp, violations)
        gates["R2"] = gate_r2(page_stats, exp, violations)
        gates["R3"] = gate_r3(pages, exp, violations)
        gates["R4"] = gate_r4(page_stats, exp, violations)
        gates["R5"] = gate_r5(page_stats, exp, violations)

        report = {
            "pdf": os.path.abspath(args.pdf),
            "expectations_file": os.path.abspath(args.expectations),
            "expectations": exp,
            "page_count": len(pages),
            "gates": {code: {"pass": ok, "detail": detail}
                      for code, (ok, detail) in sorted(gates.items())},
            "pages": page_stats,
            "violations": violations,
            "status": "pass" if not violations else "fail",
        }
        out_path = args.output or re.sub(r"\.pdf$", "", args.pdf, flags=re.I) + \
            "_render_report.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

        for code in ("R1", "R2", "R3", "R4", "R5"):
            ok, detail = gates[code]
            print("{}: {} ({})".format(code, "PASS" if ok else "FAIL", detail))
        for v in violations:
            print("{}: {}".format(v["code"], v["detail"]))
        print("render_report: {}".format(out_path))
        if violations:
            print("RENDER QA: FAIL ({} 条违例)".format(len(violations)))
            return 1
        print("RENDER QA: PASS")
        return 0
    except UsageError as exc:
        print("render_qa 用法/IO/工具错误: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
