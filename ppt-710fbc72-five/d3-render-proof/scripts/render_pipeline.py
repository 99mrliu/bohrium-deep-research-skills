#!/usr/bin/env python3
"""render_pipeline.py — 本 bundle 的核心：导出 + 逐页像素级 QA。

链路：deck.pptx --soffice--> deck.pdf --pdftoppm(或 pymupdf 兜底)--> preview/slide-N.png
随后用 PIL 逐页做栅格检查，写 /app/output/render_proof.json：

  (a) 页数一致性   pptx 页数 vs PDF 页数
  (b) OVERFLOW     墨迹（非背景像素）进入页面外圈 2% 边框带 → 疑似文本溢出/被裁切
  (c) IMAGE-LOSS   builder 记录的每张图：渲染页对应区域是否为空白；
                   兜底：放图页整页墨迹覆盖率不得低于下限
  (d) FONT-SUB     pptx XML 请求的字体 vs fc-list 现有字体，替换列为 warn
  (e) 墨迹统计     每页 ink 覆盖率；空渲染页直接 fail

每项检查输出 pass/warn/fail + 页码。任何工具缺失只记 degraded，不中断、不伪造。
阈值与已知误报见 references/render-qa.md。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

# ---- 阈值（references/render-qa.md 有推导与误报说明） ----
FRAME_BAND_FRAC = 0.02          # 外圈 2% 边框带
INK_TOL = 30                    # 与背景色差超过该值视为墨迹
OVERFLOW_WARN = 0.0005          # 带内墨迹面积占比 ≥0.05% → warn
OVERFLOW_FAIL = 0.001           # 带内墨迹面积占比 ≥0.1%  → fail（内容被页面边缘裁切）
EMPTY_COVERAGE = 0.0005         # 整页墨迹 <0.05% → 空渲染页 fail
IMAGE_REGION_FLOOR = 0.02       # 图区域内非背景像素 <2% → 疑似丢图 fail
PAGE_INK_FLOOR_WITH_IMAGE = 0.02

SOFFICE_CANDIDATES = ["soffice",
                      "/opt/homebrew/bin/soffice",
                      "/usr/bin/soffice",
                      "/Applications/LibreOffice.app/Contents/MacOS/soffice"]


def _find_tool(candidates):
    for c in candidates:
        p = shutil.which(c) if "/" not in c else (c if os.path.exists(c) else None)
        if p:
            return p
    return None


def sha256_of(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- 导出 ----------

def export_pdf(pptx_path, outdir, renderer):
    soffice = _find_tool(SOFFICE_CANDIDATES)
    renderer["soffice"] = soffice
    if not soffice:
        renderer["degraded"] = True
        renderer["notes"].append("soffice 不可用：无法导出 PDF，像素 QA 跳过（诚实降级）")
        return None
    profile = tempfile.mkdtemp(prefix="lo-profile-")
    cmd = [soffice, "--headless", "--norestore",
           f"-env:UserInstallation=file://{profile}",
           "--convert-to", "pdf", "--outdir", outdir, pptx_path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    pdf = os.path.join(outdir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    if r.returncode != 0 or not os.path.exists(pdf):
        renderer["degraded"] = True
        renderer["notes"].append(f"soffice 导出失败: rc={r.returncode} {r.stderr.strip()[:300]}")
        return None
    return pdf


def pdf_to_pngs(pdf_path, preview_dir, dpi, renderer):
    os.makedirs(preview_dir, exist_ok=True)
    for old in os.listdir(preview_dir):
        if old.startswith("slide-") and old.endswith(".png"):
            os.remove(os.path.join(preview_dir, old))
    pdftoppm = _find_tool(["pdftoppm"])
    renderer["pdftoppm"] = pdftoppm
    prefix = os.path.join(preview_dir, "slide")
    if pdftoppm:
        r = subprocess.run([pdftoppm, "-png", "-r", str(dpi), pdf_path, prefix],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            renderer["notes"].append(f"pdftoppm 失败，改用 pymupdf: {r.stderr.strip()[:200]}")
        else:
            pngs = sorted(f for f in os.listdir(preview_dir)
                          if f.startswith("slide-") and f.endswith(".png"))
            return [os.path.join(preview_dir, f) for f in pngs]
    # pymupdf 栅格化兜底
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open(pdf_path)
        zoom = dpi / 72.0
        out = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            p = os.path.join(preview_dir, f"slide-{i + 1}.png")
            pix.save(p)
            out.append(p)
        doc.close()
        renderer["notes"].append("pdftoppm 不可用，已用 pymupdf 栅格化兜底")
        return out
    except Exception as e:  # noqa: BLE001
        renderer["degraded"] = True
        renderer["notes"].append(f"PDF 栅格化失败: {e}")
        return []


# ---------- 像素 QA ----------

def _ink_image(img, bg):
    """墨迹掩膜图（L 模式，墨迹=255）：与背景色差超过 INK_TOL 的像素。"""
    from PIL import Image, ImageChops
    bg_img = Image.new("RGB", img.size, bg)
    diff = ImageChops.difference(img, bg_img).convert("L")
    return diff.point(lambda v: 255 if v > INK_TOL else 0)


def _ink_count(mask_img, box=None):
    crop = mask_img.crop(box) if box else mask_img
    hist = crop.histogram()
    return hist[255], crop.size[0] * crop.size[1]


def _corner_bg(img):
    px = img.load()
    w, h = img.size
    pts = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]
    cols = [px[x, y][:3] for x, y in pts]
    return tuple(sum(c[i] for c in cols) // 4 for i in range(3))


def analyze_page(png_path, expected_images):
    from PIL import Image
    with Image.open(png_path) as im:
        img = im.convert("RGB")
    w, h = img.size
    bg = _corner_bg(img)
    mask_img = _ink_image(img, bg)
    ink_total, page_area = _ink_count(mask_img)
    coverage = ink_total / page_area

    bx = max(1, int(w * FRAME_BAND_FRAC))
    by = max(1, int(h * FRAME_BAND_FRAC))
    ink_band = 0
    for box in [(0, 0, w, by), (0, h - by, w, h),
                (0, by, bx, h - by), (w - bx, by, w, h - by)]:
        c, _ = _ink_count(mask_img, box)
        ink_band += c
    band_area = w * h - (w - 2 * bx) * (h - 2 * by)
    band_frac = ink_band / max(1, band_area)

    if band_frac >= OVERFLOW_FAIL:
        ov = "fail"
    elif band_frac >= OVERFLOW_WARN:
        ov = "warn"
    else:
        ov = "pass"
    checks = {
        "overflow": {"status": ov, "ink_in_frame_band": round(band_frac, 6),
                     "band_frac_of_page": FRAME_BAND_FRAC},
        "empty_render": {"status": "fail" if coverage < EMPTY_COVERAGE else "pass",
                         "ink_coverage": round(coverage, 6)},
        "images": [],
    }
    for e in expected_images:
        if not e.get("embedded"):
            checks["images"].append({"ref": e.get("ref", ""), "status": "fail",
                                     "detail": f"构建期即未嵌入：{e.get('path','')}"})
            continue
        x0 = int(e["left_frac"] * w); x1 = int((e["left_frac"] + e["width_frac"]) * w)
        y0 = int(e["top_frac"] * h); y1 = int((e["top_frac"] + e["height_frac"]) * h)
        ink_r, area_r = _ink_count(mask_img, (x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)))
        frac = ink_r / max(1, area_r)
        page_floor_ok = coverage >= PAGE_INK_FLOOR_WITH_IMAGE
        status = "pass" if (frac >= IMAGE_REGION_FLOOR or page_floor_ok and frac > 0) else "fail"
        if status == "pass" and frac < IMAGE_REGION_FLOOR:
            status = "warn"  # 区域偏白但整页有墨迹：白底图可能误报，降级 warn
        checks["images"].append({"ref": e.get("ref", ""), "status": status,
                                 "region_ink_frac": round(frac, 6),
                                 "floor": IMAGE_REGION_FLOOR})
    return {"ink_coverage": round(coverage, 6), "checks": checks}


# ---------- 字体 ----------

def font_report(pptx_path):
    requested = set()
    try:
        with zipfile.ZipFile(pptx_path) as z:
            for name in z.namelist():
                if name.endswith(".xml"):
                    data = z.read(name).decode("utf-8", "ignore")
                    requested.update(re.findall(r'typeface="([^"+][^"]*)"', data))
    except Exception as e:  # noqa: BLE001
        return {"requested": [], "missing": [], "status": "warn",
                "detail": f"无法解析 pptx 字体: {e}"}
    fc = _find_tool(["fc-list"])
    if not fc:
        return {"requested": sorted(requested), "missing": sorted(requested),
                "status": "warn", "detail": "fc-list 不可用，字体核对降级为仅列出请求字体"}
    r = subprocess.run([fc, ":", "family"], capture_output=True, text=True, timeout=60)
    fams = set()
    for line in r.stdout.splitlines():
        for fam in line.split(","):
            fams.add(fam.strip().lower())
    missing = sorted(f for f in requested if f.lower() not in fams)
    return {"requested": sorted(requested), "missing": missing,
            "status": "warn" if missing else "pass",
            "detail": "缺失字体将被渲染器替换，可能影响版式" if missing else ""}


# ---------- 主流程 ----------

def render_and_qa(work_dir, output_dir, fix_log=None, run=1):
    """完整跑一遍 导出→栅格→QA，重写 render_proof.json（保留 fix_log 累计）。"""
    from pptx import Presentation
    deck = os.path.join(work_dir, "deck.pptx")
    build_log_path = os.path.join(work_dir, "build_log.json")
    with open(build_log_path, encoding="utf-8") as f:
        build_log = json.load(f)
    prs = Presentation(deck)
    n_pptx = len(prs.slides)

    renderer = {"soffice": None, "pdftoppm": None, "degraded": False, "notes": []}
    pdf = export_pdf(deck, output_dir, renderer)
    pages = []
    n_pdf = 0
    if pdf:
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            with fitz.open(pdf) as doc:
                n_pdf = doc.page_count
        except Exception:  # noqa: BLE001
            n_pdf = -1
        pngs = pdf_to_pngs(pdf, os.path.join(output_dir, "preview"), 120, renderer)
        for i, png in enumerate(pngs):
            expected = []
            if i < len(build_log["pages"]):
                expected = build_log["pages"][i].get("images", [])
            info = analyze_page(png, expected)
            info["page"] = i + 1
            info["png"] = os.path.relpath(png, output_dir)
            pages.append(info)

    parity = "pass" if (n_pdf == n_pptx and n_pdf > 0) else (
        "fail" if not renderer["degraded"] else "warn")
    fonts = font_report(deck)

    failures = []
    for p in pages:
        c = p["checks"]
        if c["overflow"]["status"] == "fail":
            failures.append({"page": p["page"], "check": "overflow",
                             "ink_in_frame_band": c["overflow"]["ink_in_frame_band"]})
        if c["empty_render"]["status"] == "fail":
            failures.append({"page": p["page"], "check": "empty_render"})
        for im in c["images"]:
            if im["status"] == "fail":
                failures.append({"page": p["page"], "check": "image_loss",
                                 "ref": im.get("ref", "")})
    if parity == "fail":
        failures.append({"page": None, "check": "page_parity",
                         "pptx": n_pptx, "pdf": n_pdf})

    worst = "pass"
    def bump(s):
        nonlocal worst
        order = {"pass": 0, "warn": 1, "fail": 2}
        if order.get(s, 0) > order[worst]:
            worst = s
    bump(parity if parity != "fail" else "fail")
    bump(fonts["status"])
    for p in pages:
        bump(p["checks"]["overflow"]["status"])
        bump(p["checks"]["empty_render"]["status"])
        for im in p["checks"]["images"]:
            bump(im["status"])
    overall = "degraded" if renderer["degraded"] and not pages else worst

    proof = {
        "run": run,
        "deck_pptx": os.path.relpath(deck, output_dir) if deck.startswith(output_dir) else deck,
        "deck_pdf": os.path.basename(pdf) if pdf else None,
        "deck_pdf_sha256": sha256_of(pdf) if pdf else None,
        "renderer": renderer,
        "page_count": {"pptx": n_pptx, "pdf": n_pdf, "status": parity},
        "thresholds": {"frame_band_frac": FRAME_BAND_FRAC,
                       "overflow_warn": OVERFLOW_WARN, "overflow_fail": OVERFLOW_FAIL,
                       "image_region_floor": IMAGE_REGION_FLOOR,
                       "empty_coverage": EMPTY_COVERAGE},
        "fonts": fonts,
        "pages": pages,
        "failures": failures,
        "unfixable": [],
        "overall": overall,
        "fix_log": fix_log or [],
    }
    out = os.path.join(output_dir, "render_proof.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(proof, f, ensure_ascii=False, indent=2)
    return proof


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args()
    old = {}
    rp = os.path.join(a.output, "render_proof.json")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as f:
            old = json.load(f)
    proof = render_and_qa(a.work, a.output, fix_log=old.get("fix_log", []), run=a.run)
    print(f"[render_pipeline] overall={proof['overall']} "
          f"pages={len(proof['pages'])} failures={len(proof['failures'])}")
    return 0 if proof["overall"] in ("pass", "warn") else 1


if __name__ == "__main__":
    sys.exit(main())
