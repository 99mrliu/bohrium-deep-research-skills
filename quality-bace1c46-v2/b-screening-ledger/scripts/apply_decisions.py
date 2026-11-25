#!/usr/bin/env python3
"""apply_decisions.py — 校验并应用筛选决定。

用法:
    python3 apply_decisions.py --workdir /app/work --decisions /app/work/decisions.jsonl

决定行（JSONL，每行一条）:
    {"cand_id": "C001",
     "decision": "include" | "exclude" | "uncertain",
     "criterion": "C-TOP",                # 必须来自下方内嵌目录
     "rationale": "……中文理由……",
     "evidence_quote": "……逐字摘自该候选标题/摘要……",
     "stage": "title_abstract",           # 可选，默认 title_abstract
     "rank_rationale": "……（可选，include 时建议给出）"}

逐行校验:
    1. cand_id 存在于 candidates.jsonl；
    2. decision ∈ {include, exclude, uncertain}；
    3. criterion 是已知标准 id；C-OTHER 要求 rationale ≥10 字；
    4. evidence_quote 经 NFKC + casefold + 空白折叠归一化后，必须是该候选
       “标题+摘要”归一化文本的子串 —— 绝不让无法核验的引句通过。

有效行按顺序追加进 workdir/screening.jsonl；无效行连同原因写入
workdir/rejected_decisions.jsonl。同一 cand_id 多行决定时最后一行生效，历史保留。

退出码: 0 = 至少一行有效且无异常；1 = 全部行被拒或决定文件为空；2 = 用法/IO 错误。
仅 Python 3 标准库。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

# 与 references/screening_criteria.md 保持一致的内嵌标准目录
CRITERIA = {
    "C-POP": "研究人群/对象不匹配",
    "C-TOP": "主题相关性",
    "C-DESIGN": "研究设计不符",
    "C-DATE": "发表时间窗口外",
    "C-LANG": "语言限制",
    "C-RTYPE": "文献类型不符",
    "C-DUP": "重复记录",
    "C-OTHER": "其他（必须给出 ≥10 字自由文本理由）",
}
DECISIONS = {"include", "exclude", "uncertain"}


def norm_text(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    return re.sub(r"\s+", " ", s).strip()


def load_candidates(workdir):
    cands = {}
    path = os.path.join(workdir, "candidates.jsonl")
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            cands[rec["cand_id"]] = rec
    return cands


def validate_row(row, idx, cands):
    """返回 (错误原因列表, 规范化后的决定行)。错误列表为空即有效。"""
    errs = []
    if not isinstance(row, dict):
        return ["决定行不是 JSON 对象"], None
    cid = row.get("cand_id")
    decision = row.get("decision")
    criterion = row.get("criterion")
    rationale = row.get("rationale")
    quote = row.get("evidence_quote")
    stage = row.get("stage") or "title_abstract"

    if not cid or not isinstance(cid, str):
        errs.append("缺少 cand_id")
        cand = None
    else:
        cand = cands.get(cid)
        if cand is None:
            errs.append("cand_id %s 不存在于 candidates.jsonl（可能已被去重合并，"
                        "请改用 survivor id）" % cid)
    if decision not in DECISIONS:
        errs.append("decision 必须是 include|exclude|uncertain，收到: %r" % (decision,))
    if criterion not in CRITERIA:
        errs.append("criterion %r 不在标准目录 %s 中"
                    % (criterion, sorted(CRITERIA)))
    if not isinstance(rationale, str) or not rationale.strip():
        errs.append("rationale 不能为空")
    elif criterion == "C-OTHER" and len(rationale.strip()) < 10:
        errs.append("C-OTHER 要求 rationale ≥10 字的具体自由文本理由")
    if not isinstance(quote, str) or not quote.strip():
        errs.append("evidence_quote 不能为空（必须逐字摘自该候选标题/摘要）")
    elif cand is not None:
        haystack = norm_text((cand.get("title") or "") + " "
                             + (cand.get("abstract_snippet") or ""))
        if norm_text(quote) not in haystack:
            errs.append("evidence_quote 未通过机器核验：归一化后不是 %s 标题/摘要的子串"
                        % cid)
    if not isinstance(stage, str) or not stage.strip():
        errs.append("stage 必须是非空字符串")
        stage = "title_abstract"

    if errs:
        return errs, None
    clean = {
        "cand_id": cid.strip(),
        "decision": decision,
        "criterion": criterion,
        "rationale": rationale.strip(),
        "evidence_quote": quote.strip(),
        "stage": stage.strip(),
    }
    rr = row.get("rank_rationale")
    if isinstance(rr, str) and rr.strip():
        clean["rank_rationale"] = rr.strip()
    return [], clean


def main(argv=None):
    ap = argparse.ArgumentParser(description="校验并应用筛选决定")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--decisions", required=True, help="decisions.jsonl 路径")
    args = ap.parse_args(argv)

    try:
        cands = load_candidates(args.workdir)
    except Exception as e:
        print("ERROR: 读取 candidates.jsonl 失败（先运行 init_ledger.py）: %s" % e,
              file=sys.stderr)
        return 2
    try:
        with open(args.decisions, "r", encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
    except Exception as e:
        print("ERROR: 读取 decisions 文件失败: %s" % e, file=sys.stderr)
        return 2
    if not lines:
        print("ERROR: decisions 文件为空，没有可应用的决定。", file=sys.stderr)
        return 1

    screening_path = os.path.join(args.workdir, "screening.jsonl")
    rejected_path = os.path.join(args.workdir, "rejected_decisions.jsonl")
    changes_path = os.path.join(args.workdir, "change_records.jsonl")

    n_ok = n_bad = 0
    with open(screening_path, "a", encoding="utf-8") as f_ok, \
            open(rejected_path, "a", encoding="utf-8") as f_bad, \
            open(changes_path, "a", encoding="utf-8") as f_ch:
        for i, line in enumerate(lines, 1):
            try:
                row = json.loads(line)
            except Exception as e:
                errs = ["JSON 解析失败: %s" % e]
                f_bad.write(json.dumps({"line": i, "raw": line[:500], "reasons": errs},
                                       ensure_ascii=False) + "\n")
                n_bad += 1
                continue
            errs, clean = validate_row(row, i, cands)
            if errs:
                f_bad.write(json.dumps({"line": i, "row": row, "reasons": errs},
                                       ensure_ascii=False) + "\n")
                f_ch.write(json.dumps({"action": "reject_decision", "line": i,
                                       "cand_id": row.get("cand_id") if isinstance(row, dict) else None,
                                       "reasons": errs}, ensure_ascii=False) + "\n")
                n_bad += 1
                print("REJECT line %d (%s): %s"
                      % (i, row.get("cand_id") if isinstance(row, dict) else "?", "; ".join(errs)))
            else:
                f_ok.write(json.dumps(clean, ensure_ascii=False) + "\n")
                f_ch.write(json.dumps({"action": "apply_decision",
                                       "cand_id": clean["cand_id"],
                                       "decision": clean["decision"],
                                       "criterion": clean["criterion"],
                                       "stage": clean["stage"]},
                                      ensure_ascii=False) + "\n")
                n_ok += 1

    print("applied=%d rejected=%d total=%d" % (n_ok, n_bad, n_ok + n_bad))
    if n_bad:
        print("被拒行详见 %s —— 修正后请重新投递。" % rejected_path)
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
