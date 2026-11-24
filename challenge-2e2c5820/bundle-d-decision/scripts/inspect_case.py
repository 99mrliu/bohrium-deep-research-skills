#!/usr/bin/env python3
"""inspect_case.py — case.json 模式无关探针。

用法: python3 inspect_case.py <case.json> <out.json>

case.json 的字段名不固定，本脚本递归扫描，按关键词启发式定位：
  - 候选计划/版本 (plans/versions)
  - 组织方合同 (资源/价格/预约 contracts)
  - 伦理相关涉及声明 (ethics-relevant involvements)
  - 输出契约 (output_contract)

退出码: 0 成功; 2 用法错误; 3 文件不可读或 JSON 非法。
"""
import json
import os
import sys

PLAN_KEYS = ["plan", "version", "方案", "版本", "candidate"]
CONTRACT_KEYS = ["contract", "合同", "报价", "价格", "price", "booking", "预约", "资源", "resource", "quote"]
ETHICS_KEYS = ["伦理", "ethic", "iacuc", "irb", "动物", "animal", "人体", "human", "危化", "危险", "hazard",
               "个人数据", "个人信息", "personal", "privacy", "数据合规", "biosafety", "生物安全"]
CONTRACT_OUT_KEYS = ["output_contract", "输出契约", "output contract"]


def _contains(text, needles):
    t = str(text).lower()
    return any(n.lower() in t for n in needles)


def walk(obj, path="$", hits=None):
    """递归收集命中项: (类别, JSON路径, 摘要)。"""
    if hits is None:
        hits = {"plans": [], "contracts": [], "ethics": [], "output_contract": []}
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = "%s.%s" % (path, k)
            if _contains(k, CONTRACT_OUT_KEYS):
                hits["output_contract"].append({"path": p, "preview": preview(v)})
            elif _contains(k, ETHICS_KEYS):
                hits["ethics"].append({"path": p, "preview": preview(v)})
            elif _contains(k, PLAN_KEYS):
                hits["plans"].append({"path": p, "preview": preview(v)})
            elif _contains(k, CONTRACT_KEYS):
                hits["contracts"].append({"path": p, "preview": preview(v)})
            walk(v, p, hits)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, "%s[%d]" % (path, i), hits)
    return hits


def preview(v, limit=160):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "…"


def find_case_id(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in ("case_id", "caseid", "case-id", "id") and isinstance(v, (str, int)):
                return v
        for v in obj.values():
            r = find_case_id(v)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_case_id(v)
            if r is not None:
                return r
    return None


def find_output_contract_fields(obj):
    """返回 output_contract 声明的字段名列表（若可解析）。"""
    found = []

    def rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if _contains(k, CONTRACT_OUT_KEYS):
                    if isinstance(v, dict):
                        found.extend(str(x) for x in v.keys())
                    elif isinstance(v, list):
                        found.extend(str(x) for x in v)
                    elif isinstance(v, str):
                        found.append(v)
                else:
                    rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)

    rec(obj)
    # 去重保序
    seen, out = set(), []
    for f in found:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("用法: python3 inspect_case.py <case.json> <out.json>\n")
        return 2
    src, out = argv[1], argv[2]
    try:
        with open(src, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write("错误: 无法读取或解析 %s: %s\n" % (src, e))
        return 3

    hits = walk(case)
    report = {
        "case_id": find_case_id(case),
        "output_contract_fields": find_output_contract_fields(case),
        "candidates": hits,
        "top_level_keys": list(case.keys()) if isinstance(case, dict) else [],
        "note": "启发式探测结果，字段名不固定，使用前请人工核对命中路径。",
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError as e:
        sys.stderr.write("错误: 无法写入 %s: %s\n" % (out, e))
        return 2
    print("inspect 完成: plans=%d contracts=%d ethics=%d output_contract=%d -> %s" % (
        len(hits["plans"]), len(hits["contracts"]), len(hits["ethics"]),
        len(hits["output_contract"]), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
