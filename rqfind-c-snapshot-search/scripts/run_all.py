#!/usr/bin/env python3
"""run_all.py — 一键: 建索引 → 从 case.json 派生初始查询组并检索 → 排序审计。
之后 Agent 可按需要用 expand.py 做受控扩展并追加检索,再跑 rankcheck/finalize。
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

def run(cmd):
    p = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    tail = (p.stdout or p.stderr).strip().splitlines()
    print("[%s] rc=%d %s" % (os.path.basename(cmd[0]), p.returncode, tail[-1] if tail else ""))
    return p.returncode

STOP = set("the a an of for in on with and or to from by is are was were we our this that their its as at into via over under using use used study review based recent years year focus method methods data evidence original articles research question search literature".split())

def derive_queries(case):
    q = str(case.get("research_question", ""))
    cons = case.get("constraints") or {}
    words = [w.lower() for w in re.findall(r"[A-Za-z][a-z\-]{3,}", q) if w.lower() not in STOP]
    uniq = []
    for w in words:
        if w not in uniq:
            uniq.append(w)
    main = " ".join(uniq[:4]) if uniq else ""
    tr = str(cons.get("time_range", ""))
    y = sorted(set(int(x) for x in re.findall(r"(?:19|20)\d{2}", tr)))
    y_from, y_to = (y[0], y[-1]) if y else (None, None)
    # 中文二元组必须与 index.py 的分词一致(按 CJK 连续段取重叠二元组)
    zh_parts = []
    for run_cjk in re.findall(r"[一-鿿]+", q):
        zh_parts += [run_cjk[i:i + 2] for i in range(len(run_cjk) - 1)]
    zh = " ".join(zh_parts[:12])
    return [{"label": "Q1-main", "query": main, "query_zh": zh,
             "year_from": y_from, "year_to": y_to, "exclude_type": ""}]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    run([os.path.join(HERE, "index.py"), "--input-dir", args.input_dir, "--work", args.work])
    case = json.load(open(args.case, encoding="utf-8")) if os.path.exists(args.case) else {}
    for i, spec in enumerate(derive_queries(case)):
        cmd = [os.path.join(HERE, "search.py"), "--work", args.work,
               "--query", spec["query"], "--query-zh", spec["query_zh"],
               "--label", spec["label"], "--out", args.out, "--top", "10"]
        if spec.get("year_from"):
            cmd += ["--year-from", str(spec["year_from"])]
        if spec.get("year_to"):
            cmd += ["--year-to", str(spec["year_to"])]
        run(cmd)
    run([os.path.join(HERE, "rankcheck.py"), "--work", args.work,
         "--out", args.out, "--search-dir", args.out, "--input-dir", args.input_dir])
    print(json.dumps({"ok": True,
                      "next": "可用 expand.py 扩展术语后追加 search.py,再跑 rankcheck.py 与 finalize.py"},
                     ensure_ascii=False))

if __name__ == "__main__":
    main()
