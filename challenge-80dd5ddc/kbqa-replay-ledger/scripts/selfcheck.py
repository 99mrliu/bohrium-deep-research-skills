#!/usr/bin/env python3
"""selfcheck.py — 交付前合同自检：result.json vs output_contract + 引文回验。

交付前最后一道闸门，独立于产生结果的流程重新核对：
1. result.json 存在且含 case_id，case_id 与 case.json 一致；
2. output_contract 声明的每个字段在 result.json 中存在（null 记 issue，
   因为契约字段应被实质填充；无契约时记 note 不算 issue）；
3. status 取值合法（completed/partial/failed），且 status=completed 时
   uncertainty 不得含"未完成/pending"类措辞；
4. 引文回验：result.json 全文中 [Fxx|sha8|La-Lb]"引文" 形态的坐标，
   逐条到索引（work/kb_index.json，若存在）回验文件存在、哈希前缀一致、
   引文逐字包含（去空白比对）。
产出 selfcheck_report.json；exit 0 恒成立，pass 字段是唯一权威结论。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

CITE = re.compile(r"\[(F\d+)\|([0-9a-f]{6,16})(?:\|(L?\d+)-L?(\d+))?\]\"([^\"]+)\"")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def squash(s):
    return re.sub(r"\s+", "", s)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    issues, notes, cite_results = [], [], []

    case = {}
    try:
        with open(os.path.join(a.input, "case.json"), encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError):
        notes.append("case.json unreadable; contract check skipped")
    rp = os.path.join(a.out, "result.json")
    result = None
    try:
        with open(rp, encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, json.JSONDecodeError):
        issues.append("result.json missing or invalid JSON")

    if result is not None:
        want_id = case.get("case_id") or case.get("id")
        if want_id and result.get("case_id") != want_id:
            issues.append("case_id mismatch: result=%r case=%r" % (result.get("case_id"), want_id))
        contract = case.get("output_contract") or {}
        fields = contract.get("fields") if isinstance(contract, dict) else None
        if not fields and isinstance(contract, dict):
            fields = list(contract.keys())
        if not fields and isinstance(contract, list):
            fields = [str(x) for x in contract]
        if fields:
            for fld in fields:
                if fld == "fields":
                    continue
                if fld not in result:
                    issues.append("contract field missing: %s" % fld)
                elif result[fld] is None:
                    issues.append("contract field is null: %s" % fld)
        else:
            notes.append("no output_contract declared; field check skipped")
        st = result.get("status")
        if st not in ("completed", "partial", "failed"):
            issues.append("status invalid: %r" % st)
        if st == "completed":
            for u in result.get("uncertainty", []):
                if any(k in str(u) for k in ("未完成", "pending", "待补")):
                    issues.append("status=completed but uncertainty says: %s" % str(u)[:80])

        # 引文回验
        index = None
        for name in ("kb_index.json", "suff_index.json", "catalog.json"):
            p = os.path.join(a.work, name)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    index = json.load(f)
                break
        if index:
            by_id = {e["file_id"]: e for e in index.get("files", [])}
            for m in CITE.finditer(json.dumps(result, ensure_ascii=False)):
                fid, sha8, l1, l2, quote = m.groups()
                e = by_id.get(fid)
                ok, reason = False, None
                if not e:
                    reason = "file_id_not_in_index"
                elif not (e.get("sha256") or "").startswith(sha8):
                    reason = "version_mismatch"
                else:
                    ext = e.get("extracted")
                    txt = ""
                    if ext and os.path.exists(os.path.join(a.work, ext)):
                        with open(os.path.join(a.work, ext), encoding="utf-8") as f:
                            txt = re.sub(r"^L\d+: ", "", f.read(), flags=re.M)
                    elif os.path.exists(os.path.join(a.input, e["relpath"])):
                        try:
                            with open(os.path.join(a.input, e["relpath"]),
                                      encoding="utf-8", errors="replace") as f:
                                txt = f.read()
                        except OSError:
                            reason = "file_unreadable"
                    ok = squash(quote) in squash(txt) if not reason else False
                    if not ok and not reason:
                        reason = "quote_not_found"
                cite_results.append({"file_id": fid, "sha8": sha8, "pass": ok,
                                     "reason": reason,
                                     "quote_head": quote[:40]})
                if not ok:
                    issues.append("citation failed: [%s|%s] %s" % (fid, sha8, reason))
        else:
            notes.append("no index found; citation re-verification skipped")

    report = {"schema": "kbqa-replay-ledger/selfcheck/v1",
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "pass": not issues, "issues": issues, "notes": notes,
              "citations_rechecked": cite_results}
    with open(os.path.join(a.out, "selfcheck_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"pass": not issues, "issues": issues,
                      "citations": len(cite_results)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
