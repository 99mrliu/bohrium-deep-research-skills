#!/usr/bin/env python3
"""check_exports.py — 导出回读自证（纯标准库）。

独立回读 export_bundle.py 的产物并与原始 claims.json 交叉核验：
1. claims.jsonl 可逐行解析，条数与 ID 集合 == 输入；
2. claims.csv 可被 csv 模块解析，条数与 ID 集合 == 输入，列序 == manifest；
3. review.md 与 review.html 覆盖全部断言 ID；
4. export-manifest.json 的 SHA-256 与磁盘重算一致。
全部通过 → export-check.json verdict=PASS，退出 0；任一失败 → FAIL，退出 1。
"""
import argparse
import csv
import hashlib
import json
import os
import sys

VERSION = "1.0.0"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="导出回读交叉核验")
    ap.add_argument("--claims", required=True)
    ap.add_argument("--export-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.claims, encoding="utf-8") as fh:
        payload = json.load(fh)
    expect_ids = [c.get("id") for c in payload.get("claims", [])]
    d = args.export_dir
    checks = []

    def check(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1. JSONL
    jsonl_path = os.path.join(d, "claims.jsonl")
    try:
        ids = []
        with open(jsonl_path, encoding="utf-8") as fh:
            for ln, line in enumerate(fh, 1):
                if line.strip():
                    ids.append(json.loads(line).get("id"))
        check("jsonl_parse", ids == expect_ids,
              f"{len(ids)}/{len(expect_ids)} 条，ID 集合一致={ids == expect_ids}")
    except Exception as exc:
        check("jsonl_parse", False, f"解析失败: {exc}")

    # 2. CSV
    csv_path = os.path.join(d, "claims.csv")
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        ids = [r.get("id") for r in rows]
        header = list(rows[0].keys()) if rows else []
        check("csv_parse", ids == expect_ids,
              f"{len(ids)}/{len(expect_ids)} 条，ID 集合一致={ids == expect_ids}")
    except Exception as exc:
        header = []
        check("csv_parse", False, f"解析失败: {exc}")

    # 3. manifest 与哈希、列序
    mpath = os.path.join(d, "export-manifest.json")
    try:
        with open(mpath, encoding="utf-8") as fh:
            manifest = json.load(fh)
        hash_ok = True
        bad = []
        for name, meta in manifest.get("files", {}).items():
            p = os.path.join(d, name)
            if not os.path.isfile(p) or sha256_file(p) != meta.get("sha256"):
                hash_ok = False
                bad.append(name)
        check("manifest_hashes", hash_ok,
              "全部文件哈希一致" if hash_ok else f"哈希不一致: {bad}")
        check("csv_columns", not header or header == manifest.get("csv_columns"),
              f"CSV 列序与 manifest 一致={header == manifest.get('csv_columns')}")
    except Exception as exc:
        check("manifest_hashes", False, f"manifest 读取失败: {exc}")

    # 4. review 文档覆盖
    for name in ("review.md", "review.html"):
        p = os.path.join(d, name)
        try:
            with open(p, encoding="utf-8") as fh:
                text = fh.read()
            missing = [i for i in expect_ids if str(i) not in text]
            check(f"{name}_coverage", not missing,
                  "覆盖全部 ID" if not missing else f"缺 ID: {missing}")
        except Exception as exc:
            check(f"{name}_coverage", False, f"读取失败: {exc}")

    passed = sum(1 for c in checks if c["ok"])
    report = {"tool": "check_exports", "version": VERSION,
              "case_id": payload.get("case_id"), "checks": checks,
              "verdict": "PASS" if passed == len(checks) else "FAIL"}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps({"verdict": report["verdict"],
                      "passed": f"{passed}/{len(checks)}"}, ensure_ascii=False))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
