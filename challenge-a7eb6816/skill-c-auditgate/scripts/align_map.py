#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""align_map.py — 句级双向对齐（审计门第 1 步）

源文与改写稿各自分句（中英文句读兼容），用字符 3-gram Jaccard 相似度
把每句稿映射到最相似源句；再反向扫描「关键源句」（含数字 / 图表引用 /
强度词）是否被任何稿句覆盖。

退出码：
  0  正常完成（含 degraded 模式，降级信息写入输出 JSON 的 meta）
  2  输入错误（文件缺失、为空、参数非法）
  1  内部错误

阈值（可用 --supported / --weak 调整，调整须记录到报告）：
  score >= supported(默认 0.35) -> supported
  weak(默认 0.15) <= score < supported -> weak
  score < weak -> unsupported
说明：中文学术语句改写后共用术语时 3-gram Jaccard 常见区间为 0.2~0.6；
轻度意译可能落在 weak 档，weak 不等于失实，仅表示需人工抽看。
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

VERSION = "1.0.0"

# 关键源句判定：含数字 / 图表引用 / 强度词
KEY_PAT = re.compile(
    r"\d"
    r"|图\s*\d|表\s*\d|figure|fig\.|table"
    r"|显著|首次|最优|最高|最低|突破|大幅|优于|领先|创纪录|颠覆"
    r"|significant|novel|first|breakthrough|outperform",
    re.IGNORECASE,
)

DECIMAL_PROTECT = "\x00"


def split_sentences(text):
    """中英文兼容分句。先剔除 Markdown 标题行（标题通常刻意改写，
    不参与句级对齐），再保护小数点，按句读/换行切分。"""
    lines = [ln for ln in text.splitlines() if not re.match(r"^\s*#{1,6}\s", ln)]
    t = unicodedata.normalize("NFKC", "\n".join(lines))
    t = re.sub(r"(\d)\.(\d)", r"\1" + DECIMAL_PROTECT + r"\2", t)  # 96.5 -> 96\x005
    parts = re.split(r"(?<=[。！？；!?;])|(?<=\.)\s+|\n+", t)
    out = []
    for p in parts:
        p = p.replace(DECIMAL_PROTECT, ".").strip()
        if p:
            out.append(p)
    return out


def normalize(s):
    """n-gram 前的归一化：NFKC、小写、仅保留字母数字与 CJK。"""
    s = unicodedata.normalize("NFKC", s).lower()
    return "".join(ch for ch in s if ch.isalnum() or "一" <= ch <= "鿿")


def ngrams(s, n=3):
    s = normalize(s)
    if not s:
        return set()
    if len(s) < n:
        return {s}
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def verdict_of(score, supported, weak):
    if score >= supported:
        return "supported"
    if score >= weak:
        return "weak"
    return "unsupported"


def main():
    ap = argparse.ArgumentParser(description="句级双向对齐：源文 vs 改写稿")
    ap.add_argument("source", help="源文（Markdown/纯文本）")
    ap.add_argument("draft", help="改写稿（Markdown/纯文本）")
    ap.add_argument("-o", "--outdir", default=".", help="输出目录（alignment.json/md）")
    ap.add_argument("--supported", type=float, default=0.35, help="supported 阈值（默认 0.35）")
    ap.add_argument("--weak", type=float, default=0.15, help="weak 阈值（默认 0.15）")
    ap.add_argument("--ngram", type=int, default=3, help="字符 n-gram 的 n（默认 3）")
    args = ap.parse_args()

    if not (0 < args.weak < args.supported < 1):
        print("ERROR: 需满足 0 < weak < supported < 1", file=sys.stderr)
        return 2

    src_path, drf_path = Path(args.source), Path(args.draft)
    for p in (src_path, drf_path):
        if not p.is_file():
            print(f"ERROR: 文件不存在: {p}", file=sys.stderr)
            return 2
    src_text = src_path.read_text(encoding="utf-8")
    drf_text = drf_path.read_text(encoding="utf-8")
    if not src_text.strip() or not drf_text.strip():
        print("ERROR: 源文或改写稿为空", file=sys.stderr)
        return 2

    src_sents = split_sentences(src_text)
    drf_sents = split_sentences(drf_text)

    # 降级模式：源文极短（<3 句）或稿件极短（<2 句）时对齐统计不可靠
    degraded = False
    degrade_reasons = []
    if len(src_sents) < 3:
        degraded = True
        degrade_reasons.append(f"源文仅 {len(src_sents)} 句（<3），句级对齐统计意义不足")
    if len(drf_sents) < 2:
        degraded = True
        degrade_reasons.append(f"改写稿仅 {len(drf_sents)} 句（<2），无法进行有效映射")

    src_grams = [ngrams(s, args.ngram) for s in src_sents]
    drf_grams = [ngrams(s, args.ngram) for s in drf_sents]

    # 正向：每句稿 -> 最相似源句
    draft_records = []
    for i, d in enumerate(drf_sents):
        best_j, best_score = -1, 0.0
        for j, s in enumerate(src_sents):
            sc = jaccard(drf_grams[i], src_grams[j])
            if sc > best_score:
                best_j, best_score = j, sc
        draft_records.append({
            "id": f"D{i+1}",
            "text": d,
            "best_source": f"S{best_j+1}" if best_j >= 0 else None,
            "best_source_text": src_sents[best_j] if best_j >= 0 else None,
            "score": round(best_score, 4),
            "verdict": verdict_of(best_score, args.supported, args.weak),
        })

    # 反向：关键源句是否被任何稿句覆盖（任一对得分 >= weak 即视为覆盖）
    source_records = []
    uncovered = []
    for j, s in enumerate(src_sents):
        key = bool(KEY_PAT.search(s))
        best_i, best_score = -1, 0.0
        for i in range(len(drf_sents)):
            sc = jaccard(drf_grams[i], src_grams[j])
            if sc > best_score:
                best_i, best_score = i, sc
        covered = best_score >= args.weak
        rec = {
            "id": f"S{j+1}",
            "text": s,
            "key": key,
            "covered": covered,
            "best_draft": f"D{best_i+1}" if best_i >= 0 else None,
            "best_draft_score": round(best_score, 4),
        }
        source_records.append(rec)
        if key and not covered:
            uncovered.append(rec)

    scores = [r["score"] for r in draft_records]
    mean_best = round(sum(scores) / len(scores), 4) if scores else 0.0
    low_global = bool(scores) and mean_best < args.supported
    if low_global:
        degrade_reasons.append(
            f"稿句平均最佳对齐分 {mean_best} < supported 阈值 {args.supported}，"
            "疑似整体偏离源文或阈值不适配，建议人工复核而非直接 FAIL"
        )

    result = {
        "meta": {
            "tool": "align_map.py",
            "version": VERSION,
            "mode": "degraded" if degraded else "normal",
            "degrade_reasons": degrade_reasons,
            "low_global_confidence": low_global,
            "thresholds": {"supported": args.supported, "weak": args.weak},
            "ngram": args.ngram,
            "source_file": str(src_path),
            "draft_file": str(drf_path),
            "n_source_sentences": len(src_sents),
            "n_draft_sentences": len(drf_sents),
            "mean_best_score": mean_best,
        },
        "draft_sentences": draft_records,
        "source_sentences": source_records,
        "uncovered_key_source": uncovered,
    }

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "alignment.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "alignment.md").write_text(render_md(result), encoding="utf-8")
    print(f"OK alignment.json/md -> {outdir}  "
          f"draft={len(drf_sents)} source={len(src_sents)} "
          f"uncovered_key={len(uncovered)} mode={result['meta']['mode']}")
    return 0


def render_md(res):
    m = res["meta"]
    lines = [
        "# 句级对齐报告（alignment）",
        "",
        f"- 工具：align_map.py v{m['version']}，{m['ngram']}-gram Jaccard",
        f"- 阈值：supported ≥ {m['thresholds']['supported']}，"
        f"weak ≥ {m['thresholds']['weak']}",
        f"- 模式：{m['mode']}；稿句平均最佳分：{m['mean_best_score']}",
    ]
    if m["degrade_reasons"]:
        lines.append("- 降级/提示：" + "；".join(m["degrade_reasons"]))
    lines += [
        "",
        "## 正向映射（稿句 → 源句）",
        "",
        "| 稿句 | 最佳源句 | 得分 | 判定 |",
        "|---|---|---|---|",
    ]
    for r in res["draft_sentences"]:
        lines.append(f"| {r['id']} | {r['best_source']} | {r['score']:.3f} | {r['verdict']} |")
    lines += ["", "### 稿句明细", ""]
    for r in res["draft_sentences"]:
        lines.append(f"- **{r['id']}**（{r['verdict']}，{r['score']:.3f}）{r['text']}")
        if r["best_source_text"]:
            lines.append(f"  - ↳ {r['best_source']}：{r['best_source_text']}")
    lines += ["", "## 反向覆盖（关键源句 → 稿件）", ""]
    for r in res["source_sentences"]:
        mark = "关键" if r["key"] else "普通"
        cov = "已覆盖" if r["covered"] else "**未覆盖**"
        lines.append(f"- {r['id']}（{mark}，{cov}，best={r['best_draft']} "
                     f"{r['best_draft_score']:.3f}）{r['text']}")
    lines += ["", "## 未覆盖关键源句（须核对 edit_log 中的 omit/condense 记录）", ""]
    if res["uncovered_key_source"]:
        for r in res["uncovered_key_source"]:
            lines.append(f"- ⚠ {r['id']}：{r['text']}")
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"INTERNAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)
