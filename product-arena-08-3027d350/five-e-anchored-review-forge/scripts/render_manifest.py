#!/usr/bin/env python3
"""render_manifest.py — 产物清单 manifest.json + 契约感知 result.json。

manifest.json：
  - files[]：产物根目录下每个已落盘文件的相对路径、字节数、sha256
    （不含 manifest.json、result.json 与 manifest.report.json 自身，避免自引用；算法见
    references/render-contract.md）
  - stats：块数 / 锚点数 / 页数
  - input_hashes：blocks.jsonl、page_meta.json（及可选 PDF）的 sha256
result.json：
  读 case.json，回带原 case_id；按 output_contract 列出的字段名逐个填充，
  填不了的置 null 并在 uncertainty 说明，status 标 partial；
  必含 status / sources / uncertainty / change_record。

退出码：0=成功，2=部分（契约字段有空），3=失败。
"""

import argparse
import hashlib
import json
import os
import sys

EXIT_OK, EXIT_PARTIAL, EXIT_FAIL = 0, 2, 3


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_blocks(path):
    blocks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                blocks.append(json.loads(line))
    return blocks


def main():
    ap = argparse.ArgumentParser(description="产物清单 + 契约感知 result.json")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--page-meta", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--pdf", default=None, help="可选：原始 PDF，计入 input_hashes")
    args = ap.parse_args()

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    report = {"script": "render_manifest.py", "warnings": [], "status": "failed"}

    try:
        blocks = load_blocks(args.blocks)
        with open(args.page_meta, encoding="utf-8") as f:
            pages = json.load(f)["pages"]
        with open(args.case, encoding="utf-8") as f:
            case = json.load(f)
    except Exception as e:  # noqa: BLE001
        report["warnings"].append(f"输入读取失败: {type(e).__name__}: {e}"[:300])
        return finish(report, out_dir, EXIT_FAIL)

    # ---- manifest.json ----
    files = []
    for root, _dirs, names in os.walk(out_dir):
        for name in sorted(names):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, out_dir)
            if rel in ("manifest.json", "result.json", "manifest.report.json"):
                # manifest.report.json 由本脚本在哈希巡检之后写出（finish()），
                # 原地重跑时其旧内容会被覆盖，列入清单必然哈希失配，故排除。
                continue
            files.append({"path": rel, "bytes": os.path.getsize(path),
                          "sha256": sha256_file(path)})
    files.sort(key=lambda r: r["path"])

    anchors = sorted({str(b["id"]) for b in blocks})
    stats = {"pages": len(pages), "blocks": len(blocks), "anchors": len(anchors)}
    input_hashes = {"blocks.jsonl": sha256_file(args.blocks),
                    "page_meta.json": sha256_file(args.page_meta)}
    if args.pdf and os.path.isfile(args.pdf):
        input_hashes[os.path.basename(args.pdf)] = sha256_file(args.pdf)

    manifest = {
        "schema": "anchored-review-forge/manifest@1",
        "hash_algorithm": "sha256",
        "stats": stats,
        "input_hashes": input_hashes,
        "files": files,
        "notes": "files[] 覆盖产物根目录下除 manifest.json、result.json 与 "
                 "manifest.report.json（本脚本自产，哈希巡检后才写出）外的全部文件；"
                 "复核方式：shasum -a 256 <file> 与对应 sha256 逐项比对。",
    }
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ---- result.json（契约感知）----
    overlays = sorted(f["path"] for f in files if f["path"].startswith("overlays/"))
    review_html = "review.html" if os.path.isfile(os.path.join(out_dir, "review.html")) else None

    def field_value(name):
        if name == "review_html":
            return review_html
        if name == "overlays":
            return overlays or None
        if name == "manifest":
            return "manifest.json"
        if name == "stats":
            return stats
        if name == "input_hashes":
            return input_hashes
        if name == "anchors":
            return anchors or None
        return None  # 未知字段

    uncertainty = []
    result = {"case_id": case.get("case_id")}
    contract = case.get("output_contract", [])
    if isinstance(contract, dict):
        contract = list(contract.keys())
    for name in contract:
        value = field_value(str(name))
        result[str(name)] = value
        if value is None:
            uncertainty.append(f"契约字段 {name} 无法填充，置 null")
    if not isinstance(case.get("output_contract"), (list, dict)):
        uncertainty.append("case.json 缺少 output_contract，未做契约字段填充")

    status = "partial" if uncertainty else "success"
    result.update({
        "status": status,
        "sources": ["blocks.jsonl", "page_meta.json", "overlays/*.svg",
                    "review.html", "manifest.json"],
        "uncertainty": uncertainty,
        "change_record": [
            "render_manifest.py: 对产物根目录逐文件计算 sha256 写入 manifest.json",
            "render_manifest.py: 按 case.json 的 output_contract 填充 result.json "
            f"（status={status}）",
        ],
    })
    result_path = os.path.join(out_dir, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    report.update({"status": status, "stats": stats,
                   "files_listed": len(files),
                   "contract_fields": list(contract),
                   "outputs": {"manifest": manifest_path, "result": result_path}})
    return finish(report, out_dir, EXIT_PARTIAL if uncertainty else EXIT_OK)


def finish(report, out_dir, code):
    report["exit_code"] = code
    path = os.path.join(out_dir, "manifest.report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
