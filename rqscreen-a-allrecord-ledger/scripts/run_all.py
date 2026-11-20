#!/usr/bin/env python3
"""run_all.py — 一键执行: ingest → dedupe → criteria 草案 → screen → attest。
筛查条款自动草案由 research_question 派生,Agent 核对修订后重跑 screen.py 即可。
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

STOPWORDS = set("""the a an of for in on with and or to from by is are was were be been we our this that
their its as at into via over under between among using use used study studies review based
have has had report show shows shown results demonstrate demonstrates research question
literature search paper papers evidence data method methods recent years year time range
focus focuses focus on main key related relevance relevant task deliver output input
""".split())

def run(cmd):
    p = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    tail = (p.stdout or p.stderr).strip().splitlines()
    print("[%s] rc=%d %s" % (os.path.basename(cmd[0]), p.returncode, tail[-1] if tail else ""))
    return p.returncode

def extract_year_window(case, text):
    """优先级: case.constraints 中的时间范围 > 问题文本中的年份表达。"""
    cons = case.get("constraints") or {}
    blob = json.dumps(cons, ensure_ascii=False)
    m = re.search(r"((19|20)\d{2})[-/年](\d{1,2})[-/月]?(\d{1,2})?[^\d]{0,6}((19|20)\d{2})", blob)
    if m:
        return int(m.group(1)), int(m.group(5))
    ys = sorted(set(int(y) for y in re.findall(r"(?:19|20)\d{2}", blob)))
    if ys:
        return ys[0], ys[-1]
    ys = sorted(set(int(y) for y in re.findall(r"(?:19|20)\d{2}", text)))
    if len(ys) >= 2:
        return ys[0], ys[-1]
    if len(ys) == 1 and re.search(r"以来|since|after|起", text, re.I):
        return ys[0], None
    return None, None

def auto_criteria(case, task_text):
    # 术语只从研究问题与约束中抽取,避免 task.md 的任务套话污染词表
    q = " ".join([str(case.get("research_question", "")),
                  json.dumps(case.get("constraints") or {}, ensure_ascii=False)])
    y_from, y_to = extract_year_window(case, q)
    words = re.findall(r"[A-Za-z][a-z\-]{3,}", q)
    freq = {}
    for w in words:
        w = w.lower()
        if w not in STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    terms = [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1]) if freq[w] >= 1][:12]
    return {
        "_note": "自动草案,Agent 必须对照 task.md 研究问题核对修订(年份窗/纳入词/排除词/类型/子问题词表)",
        "year_from": y_from, "year_to": y_to,
        "include_terms": terms,
        "min_term_hits": 1,
        "exclude_terms": [],
        "exclude_types": ["review", "meta-analysis", "editorial", "news"],
        "require_device_data": False,
        "subquestion_map": {},
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    if not os.path.isdir(args.input_dir):
        print(json.dumps({"ok": False, "error": "input-dir 不存在: %s" % args.input_dir}))
        sys.exit(1)
    run([os.path.join(HERE, "ingest.py"), "--input-dir", args.input_dir, "--work", args.work])
    run([os.path.join(HERE, "dedupe.py"), "--work", args.work])
    case = json.load(open(args.case, encoding="utf-8")) if os.path.exists(args.case) else {}
    task_text = ""
    for root, _, names in os.walk(args.input_dir):
        if "task.md" in names:
            task_text = open(os.path.join(root, "task.md"), encoding="utf-8", errors="replace").read()
    crit = auto_criteria(case, task_text)
    crit_path = os.path.join(args.work, "criteria.auto.json")
    json.dump(crit, open(crit_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    run([os.path.join(HERE, "screen.py"), "--work", args.work,
         "--criteria", crit_path, "--out", args.out])
    run([os.path.join(HERE, "attest.py"), "--work", args.work,
         "--out", args.out, "--input-dir", args.input_dir])
    print(json.dumps({"ok": True, "next": "核对并修订 %s -> criteria.json, 带 --overrides 重跑 screen.py, 然后 finalize.py" % crit_path}, ensure_ascii=False))

if __name__ == "__main__":
    main()
