#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe.py -- 第 0 步：开箱、固证、落 partial 骨架（契约门禁的起点）。

- 盘点 /input：每个文件 sha256 + 格式嗅探（magic bytes，不信扩展名）。
- 宽容解析 case.json：抽取 case_id 与 output_contract 字段名（dict 键 /
  字符串列表 / 含 name|field 的对象列表 三种形态都认）。
- **立即**写 /app/output/result.json partial 骨架（全部契约字段留空待填），
  保证此后任何时刻崩溃都有一份诚实 partial 在盘上。
- 写 run_state.json（阶段梯子 + 输入清单）。

退出码: 0 正常; 2 case.json 缺失/损坏（骨架仍落盘，status=failed）。
用法: python3 probe.py --input /input --work /app/work --output /app/output
"""
import argparse, hashlib, json, os, sys, time

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def sniff(path):
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return "unreadable"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "zip-or-docx"
    if head.startswith(b"{") or head.startswith(b"["):
        return "json?"
    if head.startswith((b"\\doc", b"%!")):
        return "tex-or-ps"
    return "text-or-unknown"

def contract_fields(case):
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, dict):
        return sorted(oc.keys())
    if isinstance(oc, list):
        out = []
        for x in oc:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                out.append(x.get("name") or x.get("field") or json.dumps(x, ensure_ascii=False)[:40])
        return out
    if isinstance(oc, str):
        return [s.strip() for s in oc.replace("；", ";").replace("，", ",").split(";") if s.strip()]
    return []

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    os.makedirs(a.output, exist_ok=True)

    inventory = []
    if os.path.isdir(a.input):
        for root, _, files in os.walk(a.input):
            for fn in sorted(files):
                p = os.path.join(root, fn)
                try:
                    inventory.append({"path": p, "size": os.path.getsize(p),
                                      "sha256": sha256_of(p), "sniffed": sniff(p)})
                except OSError as e:
                    inventory.append({"path": p, "error": str(e)})

    case_id, fields, case_err = None, [], None
    case_path = os.path.join(a.input, "case.json")
    try:
        with open(case_path, encoding="utf-8") as f:
            case = json.load(f)
        case_id = case.get("case_id") or case.get("id")
        fields = contract_fields(case)
    except (OSError, json.JSONDecodeError) as e:
        case_err = "case.json 读取/解析失败: %s" % e

    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    skeleton = {
        "case_id": case_id or "UNKNOWN(case.json unreadable)",
        "status": "failed" if case_err else "partial",
        "sources": [{"path": x["path"], "sha256": x.get("sha256")} for x in inventory if "sha256" in x],
        "changes": [],
        "uncertainties": [],
        "manual_confirm": [],
        "limits": ([case_err] if case_err else []) + ["run started; contract fields pending"],
        "artifacts": [],
        "created": now, "last_checkpoint": now,
    }
    for f in fields:
        skeleton[f] = ""
    rj = os.path.join(a.output, "result.json")
    with open(rj, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)
    state = {"started": now, "input_dir": a.input, "inventory": inventory,
             "case_id": case_id, "contract_fields": fields,
             "case_error": case_err,
             "stages": [{"name": "probe", "status": "done", "time": now}]}
    with open(os.path.join(a.work, "run_state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("probe: %d inputs, case_id=%s, contract fields=%s" % (
        len(inventory), case_id, fields))
    print("partial result.json skeleton ->", rj)
    if case_err:
        print("WARNING: %s（骨架已落盘，status=failed）" % case_err, file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
