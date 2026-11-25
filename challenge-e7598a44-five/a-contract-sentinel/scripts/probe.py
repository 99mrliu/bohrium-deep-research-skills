#!/usr/bin/env python3
"""probe.py — 契约探针：读 case.json，产出契约清单与 result.json 骨架（过程质量控制第一步）。

用法:
  python3 probe.py --case /input/case.json --input-dir /input --work /app/work

产出（--work 下）:
  contract_checklist.json  契约字段清单 + 输入文件清点（路径/字节/sha256）
  result.skeleton.json     含全部契约字段的空骨架（status=blocked），兜底用

纪律:
  - 只读输入，不写 /input；任何异常都落成诚实骨架，不臆造字段值；
  - case.json 缺失/损坏时 exit=2 并写出 blocked 骨架，指明缺什么。
"""
import argparse, hashlib, json, os, sys

BUILTIN_REQUIRED = ["case_id", "status", "sources", "uncertainty"]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        if isinstance(c.get("fields"), list):
            return [str(x) for x in c["fields"]]
        if isinstance(c.get("required"), list):
            return [str(x) for x in c["required"]]
        return sorted(c.keys())
    return []


def inventory(input_dir):
    files = []
    for root, _dirs, names in os.walk(input_dir):
        for n in sorted(names):
            p = os.path.join(root, n)
            try:
                files.append({"path": os.path.relpath(p, input_dir),
                              "bytes": os.path.getsize(p),
                              "sha256": sha256_of(p)})
            except OSError as e:
                files.append({"path": os.path.relpath(p, input_dir), "error": str(e)})
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)

    problems, case = [], {}
    if not os.path.isfile(args.case):
        problems.append("case.json 不存在: %s" % args.case)
    else:
        try:
            with open(args.case, encoding="utf-8") as fh:
                case = json.load(fh)
            if not isinstance(case, dict):
                problems.append("case.json 顶层不是对象")
                case = {}
        except Exception as e:
            problems.append("case.json 解析失败: %s" % e)
            case = {}

    fields = contract_fields(case)
    if not fields:
        problems.append("output_contract 缺失或为空: 无法确定交付字段")

    files = inventory(args.input_dir) if os.path.isdir(args.input_dir) else []
    if not files:
        problems.append("输入目录不存在或为空: %s" % args.input_dir)

    checklist = {
        "case_id": case.get("case_id"),
        "research_question": case.get("research_question"),
        "contract_fields": fields,
        "builtin_required": BUILTIN_REQUIRED,
        "all_required": sorted(set(fields) | set(BUILTIN_REQUIRED)),
        "input_files": files,
        "problems": problems,
    }
    with open(os.path.join(args.work, "contract_checklist.json"), "w", encoding="utf-8") as fh:
        json.dump(checklist, fh, ensure_ascii=False, indent=2)

    skeleton = {"case_id": case.get("case_id"), "status": "blocked",
                "sources": [], "uncertainty": problems or ["pipeline 尚未运行"]}
    for f in fields:
        if f not in skeleton:
            skeleton[f] = [] if not f.endswith("summary") else ""
    with open(os.path.join(args.work, "result.skeleton.json"), "w", encoding="utf-8") as fh:
        json.dump(skeleton, fh, ensure_ascii=False, indent=2)

    print(json.dumps({"ok": not problems, "contract_fields": len(fields),
                      "input_files": len(files), "problems": problems},
                     ensure_ascii=False))
    sys.exit(2 if problems else 0)


if __name__ == "__main__":
    main()
