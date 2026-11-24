#!/usr/bin/env python3
"""qc_gates.py — 验收驱动循环: 把 workorder 每条 item 编译成可执行验收断言。

子命令:
  run    --workorder W --chapters DIR --workdir D
         逐项编译 acceptance 文本 -> 断言 -> 执行 -> PASS/FAIL/MANUAL,
         输出 workdir/gates_report.json; 全 PASS 退出 0, 否则退出 1。
  manual --workdir D --item ID --verdict PASS|FAIL --reason "..."
         对编译不出的 manual 门, 由模型显式判定并记录理由(必填)。

可编译门 (DSL 详见 references/gates_dsl.md):
  absent "X"            acceptance 含 不再出现/不得出现/不出现 + 引号词 -> 全文 grep 须 0 命中
  present "X"           acceptance 含 应包含/须包含/包含 + 引号词 -> 全文 grep 须 >=1 命中
  figure_ref_integrity  acceptance 含 图表引用/图文一致 -> 图N/表N 引用须都有对应图题/表题行
编译不出 (含 "除...外" 等限定条款) -> manual 门, 模型显式判定。

总门: 全 PASS -> suggestion=complete; 否则 partial 并列出未过项。
输出确定性: detail 只用文件基名, 不含绝对路径与时间戳。
仅依赖 python3 标准库。
"""
import argparse
import json
import os
import re
import sys
import tempfile

SCHEMA = "gates-report/v1"

EN_Q = re.compile(r'"([^"]+)"')
CN_Q = re.compile(r'“([^”]+)”')
ABSENT_PAT = re.compile(r'不再出现|不得出现|不出现|禁止出现|无残留')
PRESENT_PAT = re.compile(r'应包含|须包含|必须包含|至少包含|包含|出现')
EXCEPT_PAT = re.compile(r'除.{1,12}以?外')
FIGREF_PAT = re.compile(r'(图|表).{0,6}(引用|完整)|图文一致|图表引用')
MENTION_RE = re.compile(r'([图表])(\d+)')
CAPTION_RE = re.compile(r'^\s*([图表])(\d+)\s*[:：\s]')


def atomic_write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".gates-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def extract_terms(text):
    terms = []
    for t in EN_Q.findall(text) + CN_Q.findall(text):
        if t and t not in terms:
            terms.append(t)
    return terms


def compile_item(item):
    """acceptance 文本 -> 断言描述; 编译不出返回 manual 门。"""
    acc = item.get("acceptance", "") or ""
    terms = extract_terms(acc)
    if EXCEPT_PAT.search(acc):
        return {"gate": "manual",
                "assertion": "含除外/限定条款, 机械断言会误判, 转人工判定",
                "terms": terms}
    if ABSENT_PAT.search(acc) and terms:
        return {"gate": "absent", "assertion": "grep(%s) 命中数须为 0" % terms,
                "terms": terms}
    if FIGREF_PAT.search(acc):
        return {"gate": "figure_ref_integrity",
                "assertion": "所有 图N/表N 引用须存在对应图题/表题行",
                "terms": []}
    if PRESENT_PAT.search(acc) and terms:
        return {"gate": "present", "assertion": "grep(%s) 命中数须 >= 1" % terms,
                "terms": terms}
    return {"gate": "manual",
            "assertion": "acceptance 无法编译为机械断言",
            "terms": terms}


def chapter_files(chapters_dir, target):
    all_md = sorted(f for f in os.listdir(chapters_dir) if f.endswith(".md"))
    if target and ".md" in target:
        picked = [f for f in all_md if f in target]
        return picked or all_md
    return all_md


def grep_term(chapters_dir, files, term):
    hits = []
    for f in files:
        with open(os.path.join(chapters_dir, f), encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if term in line:
                    hits.append("%s:%d" % (f, i))
    return hits


def figref_check(chapters_dir, files):
    mentions, captions = set(), set()
    for f in files:
        with open(os.path.join(chapters_dir, f), encoding="utf-8") as fh:
            for line in fh:
                for m in MENTION_RE.finditer(line):
                    mentions.add("%s%s" % (m.group(1), m.group(2)))
                mc = CAPTION_RE.match(line)
                if mc:
                    captions.add("%s%s" % (mc.group(1), mc.group(2)))
    missing = sorted(mentions - captions)
    return sorted(mentions), sorted(captions), missing


def execute_gate(compiled, chapters_dir, files):
    gate = compiled["gate"]
    if gate == "absent":
        all_hits = []
        for t in compiled["terms"]:
            all_hits += ["%s (%s)" % (h, t) for h in grep_term(chapters_dir, files, t)]
        if all_hits:
            return "FAIL", "仍有残留: %s" % all_hits
        return "PASS", "grep 0 命中: %s" % compiled["terms"]
    if gate == "present":
        missing = [t for t in compiled["terms"] if not grep_term(chapters_dir, files, t)]
        if missing:
            return "FAIL", "未找到: %s" % missing
        return "PASS", "全部找到: %s" % compiled["terms"]
    if gate == "figure_ref_integrity":
        mentions, captions, missing = figref_check(chapters_dir, files)
        detail = "引用=%s 图题/表题=%s" % (mentions, captions)
        if missing:
            return "FAIL", "%s 缺图题/表题: %s" % (detail, missing)
        return "PASS", detail
    return "MANUAL", "等待模型判定: qc_gates.py manual --item <id> --verdict PASS|FAIL --reason \"...\""


def recompute(items):
    verdicts = [it["verdict"] for it in items]
    if any(v == "FAIL" for v in verdicts):
        overall = "FAIL"
    elif any(v == "MANUAL" for v in verdicts):
        overall = "MANUAL_PENDING"
    else:
        overall = "PASS"
    failed = [it["id"] for it in items if it["verdict"] != "PASS"]
    return overall, failed


def cmd_run(args):
    with open(args.workorder, encoding="utf-8") as fh:
        wo = json.load(fh)
    items = []
    for item in wo.get("items", []):
        compiled = compile_item(item)
        files = chapter_files(args.chapters, item.get("target", ""))
        verdict, detail = execute_gate(compiled, args.chapters, files)
        entry = {
            "id": item.get("id"),
            "title": item.get("title", ""),
            "gate": compiled["gate"],
            "assertion": compiled["assertion"],
            "verdict": verdict,
            "detail": detail,
            "reason": None,
        }
        items.append(entry)
        print("[gate] item %s %s gate=%s verdict=%s"
              % (entry["id"], entry["title"], entry["gate"], verdict))
    overall, failed = recompute(items)
    report = {
        "schema": SCHEMA,
        "items": items,
        "overall": overall,
        "suggestion": "complete" if overall == "PASS" else "partial",
        "failed_items": failed,
    }
    if "note" in wo:
        report["note"] = wo["note"]
    atomic_write_json(os.path.join(args.workdir, "gates_report.json"), report)
    print("[gate] overall=%s suggestion=%s failed=%s" % (overall, report["suggestion"], failed))
    if overall != "PASS":
        raise SystemExit(1)


def cmd_manual(args):
    p = os.path.join(args.workdir, "gates_report.json")
    if not os.path.exists(p):
        sys.stderr.write("ERROR: 先运行 qc_gates.py run 生成 gates_report.json\n")
        raise SystemExit(2)
    if args.verdict not in ("PASS", "FAIL"):
        sys.stderr.write("ERROR: --verdict 只能是 PASS 或 FAIL\n")
        raise SystemExit(2)
    if not args.reason:
        sys.stderr.write("ERROR: manual 门必须给 --reason\n")
        raise SystemExit(2)
    with open(p, encoding="utf-8") as fh:
        rep = json.load(fh)
    hit = None
    for it in rep["items"]:
        if str(it["id"]) == str(args.item):
            hit = it
            break
    if hit is None:
        sys.stderr.write("ERROR: gates_report 中没有 item %s\n" % args.item)
        raise SystemExit(2)
    hit["verdict"] = args.verdict
    hit["reason"] = args.reason
    hit["detail"] = "模型判定: %s" % args.reason
    overall, failed = recompute(rep["items"])
    rep["overall"] = overall
    rep["suggestion"] = "complete" if overall == "PASS" else "partial"
    rep["failed_items"] = failed
    atomic_write_json(p, rep)
    print("[gate] item %s manual verdict=%s -> overall=%s" % (args.item, args.verdict, overall))
    if overall != "PASS":
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description="acceptance-driven QC gates (stdlib only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="编译并执行全部验收门")
    p.add_argument("--workorder", required=True)
    p.add_argument("--chapters", required=True)
    p.add_argument("--workdir", required=True)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("manual", help="manual 门的模型显式判定")
    p.add_argument("--workdir", required=True)
    p.add_argument("--item", required=True)
    p.add_argument("--verdict", required=True)
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_manual)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
