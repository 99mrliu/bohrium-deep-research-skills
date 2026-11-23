#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""案例引导：读取 /input，立即写出诚实的早期部分 result.json。

- case_id 原样保留；output_contract 全部键先镜像为 null（pending）。
- 根元数据（doi/title/authors）按任务约定只属于第一篇，不传播给第二篇。
用法：
  python3 case_bootstrap.py --input /input --out /app/output
"""
import argparse
import os
import sys

from relation_common import load_json, dump_json


def main(argv=None):
    ap = argparse.ArgumentParser(description="案例引导与早期部分结果")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    case = load_json(os.path.join(args.input, "case.json"))
    contract = case.get("output_contract") or {}
    result = {
        "case_id": case.get("case_id"),
        "skill": "03-conditioned-relation-kg",
        "status": "partial",
        "note": "早期部分结果：引导阶段，各字段待填充",
        "root_metadata_scope": "doi/title/authors 仅属于第一篇(primary)，不套用到第二篇",
        "sources": [],
        "uncertainty": ["引导阶段：尚未执行关系抽取与校验"],
        "changes": ["bootstrap: 写出早期部分 result.json"],
        "contract_mirror": {k: None for k in contract},
    }
    mat = os.path.join(args.input, "material.json")
    if os.path.exists(mat):
        result["sources"] = [
            {"source_id": m.get("source_id"), "role": m.get("role"),
             "file": m.get("file")}
            for m in load_json(mat).get("materials", [])]
    dump_json(result, os.path.join(args.out, "result.json"))
    print("bootstrap: case_id=%s contract_keys=%d -> %s/result.json"
          % (case.get("case_id"), len(contract), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
