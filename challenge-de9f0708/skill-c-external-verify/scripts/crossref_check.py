#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crossref_check.py — 对 refs.json 中的参考文献做严格预算的 Crossref/DOI 联网核验。

核心纪律：
  * 预算纪律：--max-queries（默认 12）限制**全部网络请求总数**（Crossref 查询与 DOI 解析
    共用同一计数器），每条目至多一次 Crossref 查询；预算耗尽后剩余条目标 pending_review。
  * 两信号规则：只有 (a) Crossref 检索无结果 **且** (b) DOI 不可解析（doi.org 返回 4xx）
    两个独立信号齐备，才给出 fabrication_suspected（仍需人工终裁）；
    单一"没搜到"永远只是 not_found → 待复核，绝不直接判"文献不存在"。
  * 只记录实际检索到的元数据原文；禁止凭模型记忆补任何字段。
  * 优先级：lint 标记（DOI 非法/年份异常/重复）> 缺 DOI > 其余，高优先级先用预算。
  * --offline 或网络异常：所有未查条目标 pending_review 并如实记录原因（优雅降级）；
    本脚本不产生本地可判项（那是 lint_refs.py 的职责），缺键不崩，exit 0。

用法：
  python3 crossref_check.py --input refs.json --output crossref.json \
      [--lint lint.json] [--max-queries 12] [--offline] [--timeout 10]
"""
import argparse
import datetime
import difflib
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "skill-c-external-verify/1.0 (reference verification; stdlib urllib)"}
VALID_DOI = re.compile(r'^10\.\d{4,9}/\S+$', re.IGNORECASE)
PARTICLES = {"von", "van", "de", "der", "den", "del", "la", "le", "di", "da"}


def norm_text(t):
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', (t or '').lower())


def sim(a, b):
    na, nb = norm_text(a), norm_text(b)
    if not na or not nb:
        return None
    return difflib.SequenceMatcher(None, na, nb).ratio()


def norm_surname(name):
    n = (name or '').strip().lower().replace('-', '').replace(' ', '')
    for p in PARTICLES:
        if n.startswith(p) and len(n) > len(p) + 1:
            n = n[len(p):]
    return n


def ref_surnames(authors_str):
    """从 'Zhang W, Li M, Wang H' 或 '李华, 王芳' 提取姓氏集合。"""
    out = set()
    for token in re.split(r'[,，;；]', authors_str or ''):
        token = token.strip()
        if not token:
            continue
        if re.match(r'^[\u4e00-\u9fff]', token):
            out.add(token[0])  # 中文姓氏取首字
        else:
            first = token.split()[0] if token.split() else token
            out.add(norm_surname(first))
    return {x for x in out if x}


class Budget:
    """全部网络请求共用的计数器。"""

    def __init__(self, max_queries):
        self.max = max_queries
        self.used = 0

    @property
    def remaining(self):
        return self.max - self.used

    def spend(self):
        if self.remaining <= 0:
            return False
        self.used += 1
        return True


def http_json(url, timeout):
    """GET JSON。返回 (status, data, error)。404 是确定答案不是网络错误。"""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return e.code, None, "HTTP %d" % e.code
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        return None, None, "network error: %s" % e
    except ValueError as e:
        return None, None, "bad json: %s" % e


def http_resolve(url, timeout):
    """解析 DOI（跟随重定向）。返回 (final_status, final_url, error)。"""
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.geturl(), None
    except urllib.error.HTTPError as e:
        if e.code in (405, 501):  # 服务器不支持 HEAD，退化为 GET
            try:
                req2 = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req2, timeout=timeout) as resp:
                    return resp.status, resp.geturl(), None
            except urllib.error.HTTPError as e2:
                return e2.code, None, "HTTP %d" % e2.code
            except (urllib.error.URLError, socket.timeout, OSError) as e2:
                return None, None, "network error: %s" % e2
        return e.code, None, "HTTP %d" % e.code
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        return None, None, "network error: %s" % e


def record_from_message(msg):
    """从 Crossref work 记录提取要比对的字段（检索到的原文，原样记录）。"""
    if not isinstance(msg, dict):
        return {}
    authors = []
    for a in msg.get("author") or []:
        if isinstance(a, dict):
            authors.append({"family": a.get("family"), "given": a.get("given")})
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        dp = ((msg.get(key) or {}).get("date-parts") or [])
        if dp and dp[0] and isinstance(dp[0][0], int):
            year = dp[0][0]
            break
    return {
        "DOI": msg.get("DOI"),
        "title": (msg.get("title") or [None])[0],
        "container-title": (msg.get("container-title") or [None])[0],
        "year": year,
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "page": msg.get("page"),
        "author": authors,
        "type": msg.get("type"),
        "URL": msg.get("URL"),
    }


def compare_fields(ref_fields, rec):
    """逐字段比对。作者拼写变体（von/连字符/大小写/名缩写）不构成 mismatch。"""
    comp = {}
    rt, ct = ref_fields.get("title"), rec.get("title")
    if rt and ct:
        s = sim(rt, ct)
        comp["title"] = {"ref": rt, "crossref": ct, "similarity": round(s, 3),
                         "verdict": "match" if s >= 0.90 else "mismatch"}
    elif rt and not ct:
        comp["title"] = {"ref": rt, "crossref": None, "verdict": "unknown"}
    ry, cy = ref_fields.get("year"), rec.get("year")
    if ry and cy:
        comp["year"] = {"ref": ry, "crossref": cy,
                        "verdict": "match" if int(ry) == int(cy) else "mismatch"}
    rj, cj = ref_fields.get("journal"), rec.get("container-title")
    if rj and cj:
        s = sim(rj, cj)
        comp["journal"] = {"ref": rj, "crossref": cj, "similarity": round(s, 3),
                           "verdict": "match" if s >= 0.80 else "mismatch"}
    ra = ref_surnames(ref_fields.get("authors"))
    ca = {norm_surname(a.get("family")) for a in rec.get("author") or [] if a.get("family")}
    if ra and ca:
        overlap = ra & ca
        ratio = len(overlap) / max(len(ra), 1)
        comp["authors"] = {"ref_surnames": sorted(ra), "crossref_surnames": sorted(ca),
                           "overlap_ratio": round(ratio, 3),
                           "verdict": "match" if ratio >= 0.6 else "mismatch",
                           "tolerance": "von/van/de 等前缀、连字符、大小写差异已归一化，不构成 mismatch"}
    for k in ("volume", "issue", "page"):
        rv, cv = ref_fields.get(k), rec.get(k)
        if rv and cv:
            comp[k] = {"ref": rv, "crossref": cv,
                       "verdict": "match" if str(rv).strip() == str(cv).strip() else "mismatch"}
    return comp


def overall_status(comp):
    verdicts = [v.get("verdict") for v in comp.values()]
    if not verdicts or all(v == "unknown" for v in verdicts):
        return "unknown"
    if any(v == "mismatch" for v in verdicts):
        key = [k for k, v in comp.items() if v.get("verdict") == "mismatch"]
        # 仅次要字段不符 → minor；标题/年份/作者不符 → major
        major_keys = {"title", "year", "authors"}
        return ("mismatch", "major" if major_keys & set(key) else "minor", key)
    return ("match", None, [])


def priority_of(ref, lint_flags):
    f = ref.get("fields") or {}
    score = 0
    flags = lint_flags.get(ref.get("index"), set())
    if "doi_format_invalid" in flags:
        score += 4
    if "year_anomaly" in flags:
        score += 4
    if "duplicate_reference" in flags:
        score += 2
    if f.get("year") and isinstance(f.get("year"), int) and f["year"] > datetime.date.today().year:
        score += 3
    doi = f.get("doi")
    if not doi:
        score += 2
    elif not VALID_DOI.match(doi):
        score += 3
    return score


def verify_one(ref, budget, timeout, query_log):
    """对单条文献执行预算内核验。返回 (result_dict, network_failed_reason_or_None)。"""
    f = ref.get("fields") or {}
    doi = f.get("doi")
    doi_valid = bool(doi and VALID_DOI.match(doi))
    res = {
        "ref_index": ref.get("index"),
        "raw_excerpt": (ref.get("raw") or "")[:200],
        "signals": {"crossref_found": None, "doi_resolvable": None},
        "retrieved_records": [],
        "field_comparison": {},
        "status": "pending_review",
        "verdict": {"type": None, "severity": None, "verdict_status": "待复核",
                    "rationale": "not yet checked"},
    }

    crossref_rec, crossref_found = None, None
    if doi_valid:
        if not budget.spend():
            res["verdict"]["rationale"] = "budget exhausted before this entry"
            return res, None
        url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        status, data, err = http_json(url, timeout)
        query_log.append({"url": url, "status": status, "error": err})
        if err and err.startswith("network"):
            return res, err
        if status == 200 and data:
            crossref_found = True
            crossref_rec = record_from_message(data.get("message"))
            res["retrieved_records"].append({"source": "crossref /works/<doi>",
                                             "record": crossref_rec})
        elif status == 404:
            crossref_found = False
        else:
            return res, "crossref query inconclusive: %s" % err
    else:
        # 无（合法）DOI → 书目检索，rows=3，仍只算一次 Crossref 查询
        q = " ".join(x for x in [f.get("title"), f.get("authors"),
                                 str(f.get("year") or "")] if x)
        if not q.strip():
            res["verdict"]["rationale"] = "no DOI and no title/authors to query"
            return res, None
        if not budget.spend():
            res["verdict"]["rationale"] = "budget exhausted before this entry"
            return res, None
        url = ("https://api.crossref.org/works?rows=3&query.bibliographic="
               + urllib.parse.quote(q))
        status, data, err = http_json(url, timeout)
        query_log.append({"url": url[:300], "status": status, "error": err})
        if err and err.startswith("network"):
            return res, err
        if status != 200 or not data:
            return res, "crossref query inconclusive: %s" % err
        items = ((data.get("message") or {}).get("items")) or []
        best, best_sim = None, 0.0
        for it in items:
            rec = record_from_message(it)
            res["retrieved_records"].append({"source": "crossref query.bibliographic",
                                             "record": rec})
            s = sim(f.get("title"), rec.get("title")) or 0.0
            if s > best_sim:
                best, best_sim = rec, s
        if best and best_sim >= 0.80:
            crossref_found, crossref_rec = True, best
        else:
            crossref_found = False
    res["signals"]["crossref_found"] = crossref_found

    # 信号 b：DOI 可解析性（仅当有合法 DOI 且预算允许）。
    # 网络异常不丢弃已检索到的 Crossref 记录：照常完成比对，仅把异常向上传递，
    # 由主循环对"后续条目"降级。
    deferred_fail = None
    if doi_valid and budget.remaining > 0:
        budget.spend()
        url = "https://doi.org/" + doi
        st, final_url, err = http_resolve(url, timeout)
        query_log.append({"url": url, "status": st, "final_url": final_url, "error": err})
        if err and err.startswith("network"):
            deferred_fail = err
        else:
            res["signals"]["doi_resolvable"] = bool(st and st < 400)

    # 判定
    if crossref_found and crossref_rec:
        comp = compare_fields(f, crossref_rec)
        res["field_comparison"] = comp
        oc = overall_status(comp)
        if oc[0] == "match":
            res["status"] = "match"
            res["verdict"] = {"type": None, "severity": None, "verdict_status": "确认",
                              "rationale": "Crossref 记录与文献著录逐字段一致。"}
        elif oc[0] == "mismatch":
            res["status"] = "mismatch"
            res["verdict"] = {"type": "metadata_mismatch", "severity": oc[1],
                              "verdict_status": "确认",
                              "rationale": "字段 %s 与 Crossref 检索记录不符；"
                                           "以 retrieved_records 中的原文为据。" % oc[2]}
        else:
            res["status"] = "unknown"
            res["verdict"]["rationale"] = "Crossref 记录字段不足，无法比对，待复核。"
    elif crossref_found is False:
        res["status"] = "not_found"
        dres = res["signals"]["doi_resolvable"]
        if doi_valid and dres is False:
            # 两信号齐备：检索无结果 + DOI 不可解析
            res["verdict"] = {"type": "fabrication_suspected", "severity": "critical",
                              "verdict_status": "待人工终裁",
                              "rationale": "两信号齐备：Crossref 无此 DOI 记录（404）且 "
                                           "doi.org 解析失败；疑似捏造文献，须人工终裁。"}
        else:
            res["verdict"] = {"type": None, "severity": None, "verdict_status": "待复核",
                              "rationale": "仅'检索无结果'单一信号，按规程不得判不存在；"
                                           "可能原因：收录延迟/预印本/小语种期刊/著录错误。"}
    if deferred_fail:
        res["verdict"]["rationale"] += "（DOI 解析请求网络异常：%s，本信号缺失）" % deferred_fail
    return res, deferred_fail


def main():
    ap = argparse.ArgumentParser(
        description="严格预算的 Crossref/DOI 参考文献核验；两信号规则；断网优雅降级。exit 0。")
    ap.add_argument("--input", required=True, help="extract_refs.py 生成的 refs.json")
    ap.add_argument("--output", required=True, help="输出 crossref.json")
    ap.add_argument("--lint", default=None, help="可选 lint.json，用于优先级排序")
    ap.add_argument("--max-queries", type=int, default=12,
                    help="全部网络请求的总预算（默认 12）")
    ap.add_argument("--timeout", type=float, default=10.0, help="单请求超时秒数（默认 10）")
    ap.add_argument("--offline", action="store_true",
                    help="离线模式：不做任何网络请求，全部条目标 pending_review")
    args = ap.parse_args()

    notes = []
    try:
        data = json.load(open(args.input, encoding="utf-8"))
    except (OSError, ValueError) as e:
        data = {}
        notes.append("cannot read/parse input: %s" % e)
    refs = data.get("refs") or []

    lint_flags = {}
    if args.lint:
        try:
            lint = json.load(open(args.lint, encoding="utf-8"))
            for c in lint.get("candidates") or []:
                for idx in c.get("ref_index") or []:
                    lint_flags.setdefault(idx, set()).add(c.get("type"))
        except (OSError, ValueError) as e:
            notes.append("cannot read lint file (ignored): %s" % e)

    budget = Budget(max(0, args.max_queries))
    ordered = sorted(refs, key=lambda r: (-priority_of(r, lint_flags),
                                          r.get("index") or 0))
    results, query_log = [], []
    network_failed = None

    if args.offline:
        notes.append("offline mode (--offline)：未发起任何网络请求；"
                     "全部条目标 pending_review，待有网时复核。")
    for ref in ordered:
        if args.offline:
            results.append({
                "ref_index": ref.get("index"),
                "raw_excerpt": (ref.get("raw") or "")[:200],
                "priority": priority_of(ref, lint_flags),
                "signals": {"crossref_found": None, "doi_resolvable": None},
                "retrieved_records": [], "field_comparison": {},
                "status": "pending_review",
                "verdict": {"type": None, "severity": None, "verdict_status": "待复核",
                            "rationale": "offline mode：外部核验未执行，"
                                         "绝不以'未检索'代替'不存在'。"},
            })
            continue
        if network_failed:
            results.append({
                "ref_index": ref.get("index"),
                "raw_excerpt": (ref.get("raw") or "")[:200],
                "priority": priority_of(ref, lint_flags),
                "signals": {"crossref_found": None, "doi_resolvable": None},
                "retrieved_records": [], "field_comparison": {},
                "status": "pending_review",
                "verdict": {"type": None, "severity": None, "verdict_status": "待复核",
                            "rationale": "network degraded: %s；后续条目不再发起请求。"
                                         % network_failed},
            })
            continue
        res, fail = verify_one(ref, budget, args.timeout, query_log)
        res["priority"] = priority_of(ref, lint_flags)
        results.append(res)
        if fail:
            network_failed = fail
            notes.append("network failure encountered: %s；其后条目全部降级为 pending_review。"
                         % fail)
    results.sort(key=lambda r: r.get("ref_index") or 0)

    status_count = {}
    for r in results:
        status_count[r["status"]] = status_count.get(r["status"], 0) + 1

    out = {
        "tool": "crossref_check.py",
        "version": "1.0",
        "mode": "offline" if args.offline else "online",
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "budget": {"max_queries": budget.max, "used": budget.used,
                   "remaining": budget.remaining},
        "two_signal_rule": "fabrication_suspected 仅在 'Crossref 检索无结果' 且 "
                           "'DOI 不可解析' 两信号齐备时给出；单一信号一律待复核。",
        "status_counts": status_count,
        "results": results,
        "query_log": query_log,
        "notes": notes,
        "caveat": "retrieved_records 为实际检索到的元数据原文；本脚本不凭模型记忆补任何字段。",
    }
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print("cannot write output: %s" % e, file=sys.stderr)
    print("crossref_check (%s): budget %d/%d used, statuses %s -> %s"
          % (out["mode"], budget.used, budget.max, status_count, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
