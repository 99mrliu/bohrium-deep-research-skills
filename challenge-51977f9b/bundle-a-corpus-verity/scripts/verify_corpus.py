#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_corpus.py — 题录真实性核验与语料治理引擎（slr-corpus-verity 签名脚本）

在筛选之前建立"可信语料层"：凡进入筛选的每条题录都必须通过元数据核验；
伪造嫌疑、重复、撤稿记录进入隔离区并给出机器可复核的理由，直接喂给
PRISMA 流程的 duplicates_removed 与排除理由计数。

核验规则：
  V1 schema 校验：缺 id 或 title → state=invalid
  V2 DOI 语法：存在 doi 且不匹配 ^10\\.d{4,9}/\\S+$ → state=suspicious（疑似伪造）
  V3 年份合理性：year 不在 [1450, 当前年+1] → state=suspicious
  V4 精确重复：规范化 DOI 相同，或 NFKC(title)+第一作者姓+year 相同 → duplicate
  V5 近似重复：规范化标题 difflib ratio >= 0.92 → probable_duplicate（与 V4 互斥，V4 优先）
  V6 撤稿信号：title/venue/note 含 retracted|retraction|withdrawn|撤稿 → retraction_flagged
  V7 语言与文献类型打标（en/zh/other；article/review/conference/unknown，不改变状态）
  V8 --online：Crossref 在线核查；网络失败 → online_check=unavailable，绝不崩溃或谎报

状态优先级：invalid > retraction_flagged > suspicious > duplicate > probable_duplicate > verified

退出码：0=通过；2=输入/材料不足（诚实降级）；3=--strict 下存在 invalid/suspicious/retraction_flagged
"""
import argparse
import datetime
import difflib
import json
import os
import re
import socket
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
YEAR_MIN = 1450
RETRACTION_RE = re.compile(r"retracted|retraction|withdrawn|撤稿", re.IGNORECASE)
NEAR_DUP_THRESHOLD = 0.92
ONLINE_TIMEOUT = 5

# 状态优先级（索引越小优先级越高）
STATE_PRIORITY = ["invalid", "retraction_flagged", "suspicious",
                  "duplicate", "probable_duplicate", "verified"]
STRICT_FAIL_STATES = {"invalid", "suspicious", "retraction_flagged"}
KNOWN_TYPES = {"article", "review", "conference"}


# ---------------------------------------------------------------- 规范化工具

def norm_text(s):
    """NFKC 规范化 + 去首尾空白 + 小写。"""
    if s is None:
        return ""
    return unicodedata.normalize("NFKC", str(s)).strip().lower()


def norm_title_key(s):
    """NFKC 规范化后去除一切非字母数字字符（标点、空格），用于重复判定。"""
    return "".join(ch for ch in norm_text(s) if ch.isalnum())


def norm_doi(d):
    """DOI 规范化：小写、去 https://doi.org/ 等前缀、去空白。"""
    t = norm_text(d)
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/",
                   "https://dx.doi.org/", "doi.org/", "doi:"):
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    return t.strip()


def first_author_surname(authors):
    """第一作者姓提取（启发式，详见 references/record_schema.md）。"""
    if isinstance(authors, list):
        if not authors:
            return ""
        first = str(authors[0])
    elif authors:
        first = re.split(r";|\s+and\s+", str(authors))[0]
    else:
        return ""
    first = norm_text(first)
    if not first:
        return ""
    if "," in first:                      # "Last, First" 形式
        return first.split(",", 1)[0].strip()
    if re.match(r"[一-鿿]", first):  # 中文姓名：姓为第一个字
        return first[0]
    parts = first.split()
    return parts[-1] if parts else ""     # 西文 "First Last"：姓为末词


def parse_year(y):
    if y is None:
        return None
    if isinstance(y, int):
        return y
    m = re.search(r"(\d{3,4})", str(y))
    return int(m.group(1)) if m else None


def detect_language(rec):
    text = "{} {}".format(rec.get("title") or "", rec.get("abstract") or "")
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cjk == 0 and latin == 0:
        return "other"
    return "zh" if cjk > latin else "en"


def detect_type(rec):
    t = norm_text(rec.get("type"))
    if t in KNOWN_TYPES:
        return t
    venue = norm_text(rec.get("venue"))
    title = norm_text(rec.get("title"))
    if re.search(r"proceeding|conference|symposium|workshop|\bconf\b|会议", venue):
        return "conference"
    if re.search(r"systematic review|meta-analysis|meta analysis|\breview\b|综述", title):
        return "review"
    if t:
        return "unknown"
    return "article" if venue else "unknown"


# ---------------------------------------------------------------- 输入装载

def load_records(path):
    """返回 (records, error)。支持 .json（数组或含 records 键的对象）与 .jsonl。"""
    if not path or not os.path.isfile(path):
        return None, "R1: records 文件缺失：{}".format(path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as e:
        return None, "R1: records 文件不可读：{}（{}）".format(path, e)
    if path.endswith(".jsonl"):
        records = []
        for i, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                return None, "R2: JSONL 第 {} 行解析失败：{}".format(i, e)
        return records, None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, "R2: JSON 解析失败：{}（第 {} 行）".format(e.msg, e.lineno)
    if isinstance(data, dict):
        for key in ("records", "references", "items", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            return None, "R3: JSON 顶层对象中未找到记录数组（records/references/items/data）"
    if not isinstance(data, list):
        return None, "R3: records 不是数组"
    return data, None


# ---------------------------------------------------------------- 在线核查（V8）

def crossref_lookup(doi):
    """返回 (message_dict, error)。任何异常都转化为 error，绝不抛出。"""
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    req = urllib.request.Request(url, headers={
        "User-Agent": "slr-corpus-verity/1.0 (synthetic skill; mailto:noreply@example.org)"})
    try:
        with urllib.request.urlopen(req, timeout=ONLINE_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
        return payload.get("message") or {}, None
    except Exception as e:  # 含 URLError/HTTPError/socket.timeout/JSON 错误
        return None, "{}: {}".format(type(e).__name__, e)


def crossref_conflict(message, rec):
    """对照在线元数据与本地记录的 title/year，返回冲突描述列表。"""
    conflicts = []
    titles = message.get("title") or []
    if titles:
        ratio = difflib.SequenceMatcher(
            None, norm_text(titles[0]), norm_text(rec.get("title") or "")).ratio()
        if ratio < 0.90:
            conflicts.append("title 不一致（在线：{}）".format(titles[0]))
    year = parse_year(rec.get("year"))
    parts = ((message.get("issued") or {}).get("date-parts") or [[None]])[0]
    if year is not None and parts and parts[0] and int(parts[0]) != year:
        conflicts.append("year 不一致（在线：{}）".format(parts[0]))
    return conflicts


# ---------------------------------------------------------------- 主核验流程

def verify(records, online=False):
    """对记录列表执行 V1–V8 核验，返回逐条结果列表。"""
    current_year_max = datetime.date.today().year + 1
    results = []

    # ---- 单条记录本地检查（V1/V2/V3/V6/V7）
    for idx, rec in enumerate(records):
        res = {
            "index": idx, "id": None, "states": [], "reasons": [],
            "checks_passed": [], "duplicate_of": None,
            "language": "other", "doctype": "unknown",
            "verification_scope": "local",
            "online_check": "disabled" if not online else "skipped",
        }
        results.append(res)
        if not isinstance(rec, dict):
            res["id"] = "<record-{}>".format(idx)
            res["states"].append("invalid")
            res["reasons"].append("V1: 记录不是 JSON 对象，无法核验")
            continue
        rid = rec.get("id")
        title = rec.get("title")
        res["id"] = str(rid).strip() if rid is not None and str(rid).strip() \
            else "<no-id-{}>".format(idx)
        # V1 schema
        if rid is None or not str(rid).strip() or title is None or not str(title).strip():
            res["states"].append("invalid")
            missing = []
            if rid is None or not str(rid).strip():
                missing.append("id")
            if title is None or not str(title).strip():
                missing.append("title")
            res["reasons"].append("V1: 缺必填字段 {} → invalid".format("/".join(missing)))
        else:
            res["checks_passed"].append("V1")
        # V2 DOI 语法（先规范化去 https://doi.org/ 等导出前缀，再做语法判定）
        doi = rec.get("doi")
        if doi is not None and str(doi).strip():
            doi_norm = norm_doi(doi)
            if DOI_RE.match(doi_norm):
                res["checks_passed"].append("V2")
            else:
                res["states"].append("suspicious")
                res["reasons"].append(
                    "V2: DOI 格式非法（{}），疑似伪造，但仅凭格式不能断言伪造 → suspicious"
                    .format(str(doi).strip()))
        else:
            res["checks_passed"].append("V2(无 DOI，跳过)")
        # V3 年份合理性
        if rec.get("year") is not None:
            year = parse_year(rec.get("year"))
            if year is None or not (YEAR_MIN <= year <= current_year_max):
                res["states"].append("suspicious")
                res["reasons"].append(
                    "V3: 年份 {} 超出合理区间 [{}, {}] → suspicious"
                    .format(rec.get("year"), YEAR_MIN, current_year_max))
            else:
                res["checks_passed"].append("V3")
        else:
            res["checks_passed"].append("V3(无年份，跳过)")
        # V6 撤稿/更正信号
        blob = " ".join(str(rec.get(k) or "") for k in ("title", "venue", "note"))
        if RETRACTION_RE.search(blob):
            res["states"].append("retraction_flagged")
            res["reasons"].append(
                "V6: title/venue/note 含撤稿信号（retracted/retraction/withdrawn/撤稿）"
                "，需人工确认后隔离 → retraction_flagged")
        else:
            res["checks_passed"].append("V6")
        # V7 语言与文献类型打标
        res["language"] = detect_language(rec)
        res["doctype"] = detect_type(rec)
        res["checks_passed"].append("V7")

    # ---- V4 精确重复（保留首条，其余标 duplicate）
    seen_doi, seen_tay = {}, {}
    for idx, rec in enumerate(records):
        res = results[idx]
        if not isinstance(rec, dict) or "invalid" in res["states"]:
            continue
        if not (rec.get("title") and str(rec.get("title")).strip()):
            continue
        doi_key = norm_doi(rec.get("doi"))
        tay_key = (norm_title_key(rec.get("title")),
                   first_author_surname(rec.get("authors")),
                   parse_year(rec.get("year")))
        hit = None
        if doi_key:
            if doi_key in seen_doi:
                hit = (seen_doi[doi_key], "规范化 DOI 相同")
            else:
                seen_doi[doi_key] = idx
        if hit is None and any(tay_key):
            if tay_key in seen_tay:
                hit = (seen_tay[tay_key], "NFKC 标题+第一作者姓+年份相同")
            else:
                seen_tay[tay_key] = idx
        if hit is not None:
            res["states"].append("duplicate")
            res["duplicate_of"] = results[hit[0]]["id"]
            res["reasons"].append(
                "V4: 精确重复（{}），保留首条 {} → duplicate".format(hit[1], res["duplicate_of"]))
        else:
            res["checks_passed"].append("V4")

    # ---- V5 近似重复（与 V4 互斥，V4 优先）
    for i, rec in enumerate(records):
        res_i = results[i]
        if not isinstance(rec, dict) or "invalid" in res_i["states"] \
                or "duplicate" in res_i["states"]:
            continue
        key_i = norm_title_key(rec.get("title"))
        if not key_i:
            continue
        best_j, best_ratio = None, 0.0
        for j in range(i):
            rec_j = records[j]
            res_j = results[j]
            if not isinstance(rec_j, dict) or "invalid" in res_j["states"]:
                continue
            key_j = norm_title_key(rec_j.get("title"))
            if not key_j:
                continue
            ratio = difflib.SequenceMatcher(None, key_i, key_j).ratio()
            if ratio >= NEAR_DUP_THRESHOLD and ratio > best_ratio:
                best_j, best_ratio = j, ratio
        if best_j is not None:
            res_i["states"].append("probable_duplicate")
            res_i["duplicate_of"] = results[best_j]["id"]
            res_i["reasons"].append(
                "V5: 近似重复（规范化标题相似度 {:.3f} ≥ {}），疑似 {} 的另一记录"
                " → probable_duplicate（建议人工复核）".format(
                    best_ratio, NEAR_DUP_THRESHOLD, res_i["duplicate_of"]))
        else:
            res_i["checks_passed"].append("V5")

    # ---- V8 在线核查（可选；失败降级，绝不崩溃）
    online_stats = {"ok": 0, "mismatch": 0, "unavailable": 0, "errors": []}
    if online:
        for idx, rec in enumerate(records):
            res = results[idx]
            if not isinstance(rec, dict) or "invalid" in res["states"]:
                continue
            doi = norm_doi(rec.get("doi"))
            if not doi or not DOI_RE.match(doi):
                continue  # 语法不合法的 DOI 不值得在线查
            message, err = crossref_lookup(doi)
            if err is not None:
                res["online_check"] = "unavailable"
                online_stats["unavailable"] += 1
                online_stats["errors"].append("{}: {}".format(res["id"], err))
                res["reasons"].append(
                    "V8: 在线核查不可用（{}）；结论仅限本地一致性核验，"
                    "不得以'快照中查不到'作为伪造证据".format(err))
                continue
            res["verification_scope"] = "online"
            conflicts = crossref_conflict(message, rec)
            if conflicts:
                res["online_check"] = "mismatch"
                online_stats["mismatch"] += 1
                res["states"].append("suspicious")
                res["reasons"].append(
                    "V8: Crossref 命中但元数据冲突（{}）→ suspicious".format("；".join(conflicts)))
            else:
                res["online_check"] = "ok"
                res["checks_passed"].append("V8(verified_online)")
                online_stats["ok"] += 1

    # ---- 汇总最终状态（按优先级）
    for res in results:
        state = "verified"
        for s in STATE_PRIORITY:
            if s in res["states"]:
                state = s
                break
        res["state"] = state
        del res["states"]
    return results, online_stats


def build_report(records, results, args, online_stats):
    summary = {s: 0 for s in STATE_PRIORITY}
    for res in results:
        summary[res["state"]] += 1
    quarantine = [{"id": r["id"], "state": r["state"], "reasons": r["reasons"]}
                  for r in results if r["state"] != "verified"]
    if not args.online:
        online_check = "disabled"
    elif online_stats["ok"] == 0 and online_stats["unavailable"] > 0:
        online_check = "unavailable"
    elif online_stats["unavailable"] > 0:
        online_check = "partial"
    else:
        online_check = "ok"
    return {
        "tool": "verify_corpus.py",
        "skill": "slr-corpus-verity",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_records": os.path.abspath(args.records),
        "online": bool(args.online),
        "online_check": online_check,
        "online_errors": online_stats["errors"],
        "thresholds": {"near_duplicate_ratio": NEAR_DUP_THRESHOLD,
                       "year_range": [YEAR_MIN, datetime.date.today().year + 1],
                       "doi_pattern": DOI_RE.pattern},
        "records": results,
        "summary": summary,
        "quarantine": quarantine,
        "prisma": {
            "identified": len(results),
            "duplicates_removed": summary["duplicate"] + summary["probable_duplicate"],
            "quarantined": summary["invalid"] + summary["suspicious"] + summary["retraction_flagged"],
            "clean_for_screening": summary["verified"],
        },
    }


def main():
    ap = argparse.ArgumentParser(
        description="题录真实性核验与语料治理引擎（V1–V8）。"
                    "退出码：0=通过；2=输入/材料不足；3=--strict 下发现 invalid/suspicious/retraction_flagged。")
    ap.add_argument("--records", required=True, help="题录文件路径（.json 或 .jsonl）")
    ap.add_argument("--out", required=True, help="corpus_report.json 输出路径")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式：存在 invalid/suspicious/retraction_flagged 时以 exit 3 结束")
    ap.add_argument("--online", action="store_true",
                    help="启用 Crossref 在线核查（V8）；网络失败自动降级，不影响退出码语义")
    args = ap.parse_args()

    records, err = load_records(args.records)
    if err is not None:
        print("[{}] {}".format(err.split(":")[0], err), file=sys.stderr)
        minimal = {
            "tool": "verify_corpus.py", "skill": "slr-corpus-verity",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "input_records": os.path.abspath(args.records), "error": err,
            "records": [], "summary": {s: 0 for s in STATE_PRIORITY},
            "quarantine": [],
            "prisma": {"identified": 0, "duplicates_removed": 0,
                       "quarantined": 0, "clean_for_screening": 0},
        }
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(minimal, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass
        print("诚实降级：输入不可用，已写出最小报告（exit 2）", file=sys.stderr)
        return 2
    if not records:
        print("[R4] 记录数为 0，材料不足，无法建立可信语料层（exit 2）", file=sys.stderr)
        return 2

    results, online_stats = verify(records, online=args.online)
    report = build_report(records, results, args, online_stats)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    p = report["prisma"]
    print("核验完成：identified={} duplicates_removed={} quarantined={} clean_for_screening={}"
          .format(p["identified"], p["duplicates_removed"], p["quarantined"], p["clean_for_screening"]))
    for q in report["quarantine"]:
        print("  隔离：{} [{}] {}".format(q["id"], q["state"], "；".join(q["reasons"])))
    if args.online:
        print("在线核查状态：{}".format(report["online_check"]))

    if args.strict:
        bad = [r for r in results if r["state"] in STRICT_FAIL_STATES]
        if bad:
            print("[V-STRICT] 严格模式失败：{} 条记录处于 invalid/suspicious/retraction_flagged"
                  "（exit 3）".format(len(bad)), file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
