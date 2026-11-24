#!/usr/bin/env python3
"""index_sources.py — 把材料目录切成带定位的 span，输出 spans.json。

- .txt/.md：按行滑窗建 span，span_id 形如 "<文件名>#L<起>-<止>"；
  --mode paragraphs 时按空行分段，span_id 形如 "<文件名>#S<n>"。
- .json/.jsonl：题录文件，每条记录建一个 span，
  span_id 形如 "<文件名>#<record_id>"（无 id 时用 J001、J002……）。
输出 spans.json：{ "__meta__": {...}, "<span_id>": {"source","locator","text"} }。

完全确定性：无时间戳、无随机；同一输入重跑输出逐字节一致。
退出码：0=成功；2=材料缺失/无法建索引；3=校验失败。
"""
import argparse
import json
import os
import re
import sys

WINDOW = 6   # 行滑窗宽度（行）
STEP = 3     # 行滑窗步长（行），窗口间有重叠，保证跨行 quote 可整体命中
TEXT_EXT = (".txt", ".md")
RECORD_EXT = (".json", ".jsonl")


def fail_input(msg):
    print(f"[E-INPUT] {msg}", file=sys.stderr)
    sys.exit(2)


def index_text_lines(fname, content, spans):
    lines = content.splitlines()
    n = len(lines)
    if n == 0:
        return 0
    starts = set(range(0, n, STEP))
    starts.add(max(0, n - WINDOW))
    count = 0
    for s in sorted(starts):
        e = min(s + WINDOW, n)
        span_id = f"{fname}#L{s + 1}-{e}"
        spans[span_id] = {
            "source": fname,
            "locator": f"L{s + 1}-{e}",
            "text": "\n".join(lines[s:e]),
        }
        count += 1
    return count


def index_text_paragraphs(fname, content, spans):
    paras = re.split(r"\n[ \t]*\n", content)
    count = 0
    for i, p in enumerate(paras, 1):
        text = p.strip("\n")
        if not text.strip():
            continue
        span_id = f"{fname}#S{i}"
        spans[span_id] = {"source": fname, "locator": f"S{i}", "text": text}
        count += 1
    return count


def iter_records(fname, content):
    """从题录文件产出记录列表；解析失败返回 None。"""
    if fname.endswith(".jsonl"):
        records = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                return None
        return records
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("records", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return None


def index_records(fname, content, spans):
    records = iter_records(fname, content)
    if records is None:
        print(f"[W-PARSE] 题录文件 {fname} 无法解析为 JSON/JSONL，已跳过。", file=sys.stderr)
        return 0
    count = 0
    for i, rec in enumerate(records, 1):
        if not isinstance(rec, dict):
            rec = {"value": rec}
        rid = rec.get("record_id") or rec.get("id") or f"J{i:03d}"
        span_id = f"{fname}#{rid}"
        spans[span_id] = {
            "source": fname,
            "locator": str(rid),
            "text": json.dumps(rec, ensure_ascii=False, sort_keys=True),
        }
        count += 1
    return count


def main():
    ap = argparse.ArgumentParser(
        description="把材料目录中的 .txt/.md/.json/.jsonl 切成带定位的 span，输出 spans.json。")
    ap.add_argument("--sources", required=True, help="材料目录")
    ap.add_argument("--out", required=True, help="输出 spans.json 路径")
    ap.add_argument("--mode", choices=["lines", "paragraphs"], default="lines",
                    help="文本切分方式：lines=行滑窗（默认），paragraphs=按段落")
    args = ap.parse_args()

    if not os.path.isdir(args.sources):
        fail_input(f"材料目录不存在：{args.sources}")

    spans = {}
    files_used = []
    for root, dirs, files in os.walk(args.sources):
        dirs.sort()
        for fname in sorted(files):
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, args.sources)
            lower = fname.lower()
            if not lower.endswith(TEXT_EXT + RECORD_EXT):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError) as e:
                print(f"[W-READ] 无法读取 {rel}：{e}，已跳过。", file=sys.stderr)
                continue
            if lower.endswith(TEXT_EXT):
                if args.mode == "lines":
                    made = index_text_lines(rel, content, spans)
                else:
                    made = index_text_paragraphs(rel, content, spans)
            else:
                made = index_records(rel, content, spans)
            if made > 0:
                files_used.append({"file": rel, "spans": made})

    if not spans:
        fail_input(
            f"材料目录 {args.sources} 中没有可建索引的 .txt/.md/.json/.jsonl 文件，"
            "请先用 pdftotext -layout 或 OCR 把 PDF 转为 UTF-8 文本。")

    out = {"__meta__": {
        "tool": "index_sources.py",
        "mode": args.mode,
        "window": WINDOW,
        "step": STEP,
        "files": files_used,
        "span_count": len(spans),
    }}
    out.update(spans)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"已生成 {args.out}：{len(files_used)} 个文件，{len(spans)} 个 span（mode={args.mode}）。")
    sys.exit(0)


if __name__ == "__main__":
    main()
