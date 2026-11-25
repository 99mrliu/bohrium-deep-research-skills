#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recall_estimator.py — 多数据库联合检索的召回统计估计（capture–recapture）。

把多来源文献检索视为捕获-再捕获问题：先做最小身份归并得到"簇 × 来源"的
捕获历史矩阵，再据此用 Chapman（两库）与 Chao1（多库）估计未检出的相关
记录数，给出置信区间、各库独有贡献与条件覆盖，并生成可辩护的遗漏陈述。

纯 Python 3 标准库；离线；确定性；幂等。退出码：
  0  正常完成（分析性降级如 descriptive-only 体现在 status/flag，不影响退出码）
  2  诚实降级（顶层异常被捕获，或存在无法填充的契约字段，仍写出诚实 result.json）
  3  输入无效（case.json 缺失或不可解析）

子命令：parse / estimate / report / finalize / selfcheck / run-all
"""
import argparse
import csv
import hashlib
import json
import math
import os
import sys
import unicodedata

SKILL_NAME = "recall-capture-recapture"
VERSION = "1.0.0"
ROUND = 4
Z95 = 1.96

# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------


def r4(x):
    """确定性四舍五入到 ROUND 位小数（None 透传）。"""
    if x is None:
        return None
    return round(float(x), ROUND)


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 字段规范化（最小身份归并所需的全部规范化）
# ---------------------------------------------------------------------------


def norm_doi(raw):
    if raw is None:
        return None
    d = str(raw).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.strip().strip("/").rstrip(".")
    return d or None


def norm_pmid(raw):
    if raw is None:
        return None
    p = str(raw).strip()
    return p or None


def norm_title(raw):
    """标题规范化：NFKD 分解、去变音符、小写、仅保留字母数字与空格、压缩空白。"""
    if not raw:
        return None
    t = unicodedata.normalize("NFKD", str(raw))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower()
    t = "".join(ch if (ch.isalnum()) else " " for ch in t)
    t = " ".join(t.split())
    return t or None


def norm_surname(raw):
    """从 'Zhang, Wei' / 'Wei Zhang' / 'Zhang W' 中取姓并规范化。"""
    if not raw:
        return None
    s = str(raw).strip()
    if "," in s:
        s = s.split(",", 1)[0]
    else:
        parts = s.split()
        s = parts[-1] if parts else ""
    s = norm_title(s)
    return s or None


def norm_year(raw):
    if raw is None:
        return None
    try:
        y = int(str(raw).strip()[:4])
        return y if 1000 <= y <= 2999 else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 材料嗅探与记录抽取
# ---------------------------------------------------------------------------


def sniff_json_payload(payload, basename):
    """返回 (kind, records_or_None)。kind ∈ crossref/europepmc/publisher_json/
    reference_graph/import_state/truth/case/unknown。"""
    lower = basename.lower()
    if isinstance(payload, dict):
        if "true_total_distinct_papers" in payload:
            return "truth", None
        if "output_contract" in payload and "case_id" in payload:
            return "case", None
        msg = payload.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            return "crossref", msg["items"]
        rl = payload.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return "europepmc", rl["result"]
        if isinstance(payload.get("records"), list):
            return "publisher_json", payload["records"]
        if "nodes" in payload or "edges" in payload:
            return "reference_graph", None
        if "imported_records" in payload or "last_import" in payload or \
           "import_state" in lower:
            return "import_state", None
        return "unknown", None
    if isinstance(payload, list):
        return "publisher_json", payload
    return "unknown", None


def extract_crossref(item):
    authors = item.get("author") or []
    surname = None
    if authors and isinstance(authors[0], dict):
        surname = norm_surname(authors[0].get("family"))
    title = None
    tl = item.get("title")
    if isinstance(tl, list) and tl:
        title = str(tl[0])
    elif isinstance(tl, str):
        title = tl
    year = None
    issued = item.get("issued")
    if isinstance(issued, dict):
        dp = issued.get("date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            year = norm_year(dp[0][0])
    return {"doi": norm_doi(item.get("DOI")),
            "pmid": norm_pmid(item.get("PMID")),
            "title": title, "year": year, "first_author_surname": surname}


def extract_europepmc(item):
    surname = None
    au = item.get("authorString")
    if au:
        # EuropePMC authorString 形如 "Zhang W, Li H"：第一作者段的首个词为姓
        first_author = str(au).split(",")[0].strip()
        first_token = first_author.split()[0] if first_author.split() else ""
        surname = norm_surname(first_token)
    return {"doi": norm_doi(item.get("doi")),
            "pmid": norm_pmid(item.get("pmid") or item.get("id")),
            "title": item.get("title"),
            "year": norm_year(item.get("pubYear")),
            "first_author_surname": surname}


def extract_publisher(item):
    surname = None
    authors = item.get("authors")
    if isinstance(authors, list) and authors:
        surname = norm_surname(authors[0])
    elif isinstance(authors, str) and authors.strip():
        surname = norm_surname(authors.split(";")[0])
    return {"doi": norm_doi(item.get("doi")),
            "pmid": norm_pmid(item.get("pmid")),
            "title": item.get("title"),
            "year": norm_year(item.get("year")),
            "first_author_surname": surname}


EXTRACTORS = {
    "crossref": extract_crossref,
    "europepmc": extract_europepmc,
    "publisher_json": extract_publisher,
    "publisher_jsonl": extract_publisher,
    "publisher_csv": extract_publisher,
}

KIND_TO_SOURCE = {
    "crossref": "crossref",
    "europepmc": "europepmc",
    "publisher_json": "publisher",
    "publisher_jsonl": "publisher",
    "publisher_csv": "publisher",
}


def load_material_records(path, notes):
    """嗅探单个材料文件，返回 (kind, [规范化记录])。无法识别的返回 (kind, [])。"""
    base = os.path.basename(path)
    lower = base.lower()
    try:
        if lower.endswith(".csv"):
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            return "publisher_csv", rows
        if lower.endswith(".jsonl"):
            rows = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
            return "publisher_jsonl", rows
        if lower.endswith(".json"):
            payload = read_json(path)
            return sniff_json_payload(payload, base)
        notes.append("未识别的扩展名，跳过: %s" % base)
        return "unknown", None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, csv.Error) as exc:
        notes.append("材料读取失败 %s: %s" % (base, exc))
        return "unreadable", None


# ---------------------------------------------------------------------------
# 并查集（最小身份归并）
# ---------------------------------------------------------------------------


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        p = self.parent.setdefault(x, x)
        if p != x:
            self.parent[x] = self.find(p)
        return self.parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def resolve_identities(records):
    """records: [{uid, source, doi, pmid, title, year, first_author_surname}]。
    返回 (clusters_membership, match_stats)。
    键：DOI 精确；PMID 精确；规范化标题+年份+第一作者姓 复合键。"""
    uf = UnionFind()
    key_owner = {}
    match_stats = {"doi_edges": 0, "pmid_edges": 0, "fuzzy_edges": 0}
    for rec in records:
        uid = rec["uid"]
        uf.find(uid)
        keys = []
        if rec.get("doi"):
            keys.append(("doi", rec["doi"]))
        if rec.get("pmid"):
            keys.append(("pmid", rec["pmid"]))
        nt = norm_title(rec.get("title"))
        if nt and rec.get("year") and rec.get("first_author_surname"):
            keys.append(("fuzzy", nt, rec["year"], rec["first_author_surname"]))
        rec["_norm_title"] = nt
        rec["_keys"] = [k[0] for k in keys]
        for key in keys:
            if key in key_owner:
                uf.union(uid, key_owner[key])
                match_stats[key[0] + "_edges"] += 1
            else:
                key_owner[key] = uid
    groups = {}
    for rec in records:
        groups.setdefault(uf.find(rec["uid"]), []).append(rec)
    return groups, match_stats


def build_clusters(groups, sources):
    """确定性排序分簇，返回簇列表。排序键：簇内最小 uid。"""
    ordered = sorted(groups.values(), key=lambda ms: min(m["uid"] for m in ms))
    clusters = []
    for idx, members in enumerate(ordered, start=1):
        cid = "C%03d" % idx
        srcs = sorted({m["source"] for m in members},
                      key=lambda s: sources.index(s) if s in sources else len(sources))
        pattern = "".join("1" if s in srcs else "0" for s in sources)
        # 代表字段：优先带 DOI 的成员，标题取最长（确定性 tie-break）
        rep = sorted(members, key=lambda m: (0 if m.get("doi") else 1, m["uid"]))[0]
        titles = [m.get("title") for m in members if m.get("title")]
        best_title = sorted(titles, key=lambda t: (-len(t), t))[0] if titles else None
        fuzzy_only = bool(members) and all(
            "doi" not in m.get("_keys", []) and "pmid" not in m.get("_keys", [])
            for m in members)
        multi_source = len(srcs) > 1
        fuzzy_linked = False
        if multi_source:
            # 该簇若没有任何跨源 DOI/PMID 共享键，则其跨源链接仅由模糊键造成
            by_key = {}
            for m in members:
                for k in ("doi", "pmid"):
                    v = m.get(k)
                    if v:
                        by_key.setdefault((k, v), set()).add(m["source"])
            fuzzy_linked = not any(len(v) > 1 for v in by_key.values())
        clusters.append({
            "cluster_id": cid,
            "pattern": pattern,
            "sources": srcs,
            "member_records": sorted(m["uid"] for m in members),
            "n_member_records": len(members),
            "representative": {
                "doi": rep.get("doi"),
                "pmid": rep.get("pmid"),
                "title": best_title or rep.get("title"),
                "year": rep.get("year"),
                "first_author_surname": rep.get("first_author_surname"),
            },
            "fuzzy_only_cross_source_link": fuzzy_linked,
        })
    return clusters


# ---------------------------------------------------------------------------
# 估计量（公式见 references/estimators.md）
# ---------------------------------------------------------------------------


def chapman_pair(n_i, n_j, m_ij):
    """Chapman (1951) 偏差校正 Lincoln–Petersen 估计与方差。
    m_ij == 0 时估计无定义，返回 status=undefined_zero_overlap。"""
    if m_ij == 0:
        return {"status": "undefined_zero_overlap", "N_hat": None,
                "variance": None, "se": None, "ci95": None}
    n_hat = ((n_i + 1.0) * (n_j + 1.0)) / (m_ij + 1.0) - 1.0
    var = ((n_i + 1.0) * (n_j + 1.0) * (n_i - m_ij) * (n_j - m_ij)) / \
          (((m_ij + 1.0) ** 2) * (m_ij + 2.0))
    se = math.sqrt(var)
    lo = max(max(n_i, n_j), n_hat - Z95 * se)
    hi = n_hat + Z95 * se
    return {"status": "ok", "N_hat": r4(n_hat), "variance": r4(var),
            "se": r4(se), "ci95": [r4(lo), r4(hi)]}


def chao1_estimate(s_obs, f1, f2):
    """Chao (1987) Chao1 下界估计 + 对数变换 95% CI。
    f2 == 0 时使用偏差校正形式 f1(f1-1)/2。"""
    if f2 > 0:
        variant = "classic"
        n_hat = s_obs + (f1 ** 2) / (2.0 * f2)
        ratio = f1 / float(f2)
        var = f2 * (0.25 * ratio ** 4 + ratio ** 3 + 0.5 * ratio ** 2)
    else:
        variant = "bias_corrected_f2_zero"
        n_hat = s_obs + f1 * (f1 - 1.0) / 2.0
        if n_hat > 0:
            var = f1 * (f1 - 1.0) / 2.0 \
                + f1 * ((2.0 * f1 - 1.0) ** 2) / 4.0 \
                - (f1 ** 4) / (4.0 * n_hat)
        else:
            var = 0.0
    t = n_hat - s_obs
    if t <= 0:
        ci = [float(s_obs), float(s_obs)]
        c_factor = None
    else:
        c_factor = math.exp(Z95 * math.sqrt(math.log(1.0 + var / (t ** 2))))
        ci = [s_obs + t / c_factor, s_obs + t * c_factor]
    unseen = max(0.0, n_hat - s_obs)
    unseen_ci = [max(0.0, ci[0] - s_obs), max(0.0, ci[1] - s_obs)]
    return {"variant": variant, "S_obs": s_obs, "f1": f1, "f2": f2,
            "N_hat": r4(n_hat), "variance": r4(var),
            "log_ci_factor": r4(c_factor),
            "ci95": [r4(ci[0]), r4(ci[1])],
            "unseen_estimate": r4(unseen),
            "unseen_ci95": [r4(unseen_ci[0]), r4(unseen_ci[1])]}


def compute_census(capture_histories):
    """从 capture_histories.json 重算全部公式输入（selfcheck 复用同一函数）。"""
    sources = capture_histories["sources"]
    matrix = capture_histories["matrix"]
    n_i = {s: 0 for s in sources}
    for row in matrix:
        for s in sources:
            if row[s] == 1:
                n_i[s] += 1
    m_ij = {}
    for a in range(len(sources)):
        for b in range(a + 1, len(sources)):
            sa, sb = sources[a], sources[b]
            m_ij[sa + "|" + sb] = sum(
                1 for row in matrix if row[sa] == 1 and row[sb] == 1)
    s_obs = len(matrix)
    f1 = sum(1 for row in matrix if sum(row[s] for s in sources) == 1)
    f2 = sum(1 for row in matrix if sum(row[s] for s in sources) == 2)
    return {"sources": sources, "S_obs": s_obs, "n_i": n_i,
            "m_ij": m_ij, "f1": f1, "f2": f2}


def small_sample_check(census):
    reasons = []
    for s, n in census["n_i"].items():
        if n < 5:
            reasons.append("来源 %s 检出簇数 %d < 5" % (s, n))
    if census["S_obs"] < 10:
        reasons.append("总簇数 %d < 10" % census["S_obs"])
    return reasons


ASSUMPTIONS = [
    "封闭总体：检索材料快照期间，相关文献总体不变（无新增/撤稿进入样本）",
    "各库检出概率允许异质，但簇间的重叠结构携带关于未检出簇数量的信息",
    "无行为响应：被某库检出不改变该记录被其他库检出的概率",
    "身份归并正确：DOI/PMID 精确键与 标题+年份+第一作者姓 复合键的归并错误可忽略",
    "Chao1 是下界估计：真实总数 ≥ 点估计的倾向成立，但不保证等于点估计",
    "点估计 ≠ 真实总数：必须与观测事实（S_obs、f1、f2、n_i）成对呈现",
]


# ---------------------------------------------------------------------------
# 子命令：parse
# ---------------------------------------------------------------------------


def find_material_paths(input_dir, case):
    """按 case.json materials 清单 + 目录扫描发现材料文件（确定性排序）。"""
    found = []
    seen = set()
    for name in case.get("materials", []) or []:
        candidates = [os.path.join(input_dir, name),
                      os.path.join(input_dir, os.path.basename(name)),
                      os.path.join(input_dir, "materials", os.path.basename(name))]
        hit = next((c for c in candidates if os.path.isfile(c)), None)
        if hit and hit not in seen:
            seen.add(hit)
            found.append(hit)
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for fn in sorted(files):
            if not fn.lower().endswith((".json", ".jsonl", ".csv")):
                continue
            p = os.path.join(root, fn)
            if p not in seen and os.path.basename(p) != "case.json":
                seen.add(p)
                found.append(p)
    return found


def cmd_parse(args):
    notes = []
    case_path = args.case or os.path.join(args.input, "case.json")
    if not os.path.isfile(case_path):
        sys.stderr.write("ERROR: case.json 不存在: %s\n" % case_path)
        return 3
    try:
        case = read_json(case_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("ERROR: case.json 不可解析: %s\n" % exc)
        return 3

    paths = find_material_paths(args.input, case)
    source_order = list(case.get("source_dbs") or [])
    per_source_records = {}
    used_files = []
    aux_files = []
    for path in paths:
        kind, raw = load_material_records(path, notes)
        base = os.path.basename(path)
        if kind in EXTRACTORS:
            source = KIND_TO_SOURCE[kind]
            if source not in source_order:
                source_order.append(source)
            extractor = EXTRACTORS[kind]
            bucket = per_source_records.setdefault(source, [])
            for item in raw or []:
                rec = extractor(item if isinstance(item, dict) else {})
                rec["source"] = source
                rec["source_file"] = base
                bucket.append(rec)
            used_files.append({"file": base, "kind": kind, "source": source,
                               "records": len(raw or [])})
        elif kind in ("reference_graph", "import_state", "truth", "case"):
            aux_files.append({"file": base, "kind": kind})
        else:
            notes.append("材料未能识别或读取，未纳入捕获历史: %s (kind=%s)"
                         % (base, kind))
    # 规范来源顺序：case.json 声明优先，其后按字母序
    declared = [s for s in (case.get("source_dbs") or []) if s in per_source_records]
    extras = sorted(s for s in per_source_records if s not in declared)
    sources = declared + extras

    # 赋 uid 并做身份归并
    all_records = []
    for s in sources:
        for i, rec in enumerate(per_source_records.get(s, []), start=1):
            rec = dict(rec)
            rec["uid"] = "%s#%04d" % (s, i)
            all_records.append(rec)
    groups, match_stats = resolve_identities(all_records)
    clusters = build_clusters(groups, sources)

    # 捕获历史矩阵与历史计数
    histories = {}
    matrix = []
    for cl in clusters:
        row = {"cluster_id": cl["cluster_id"], "pattern": cl["pattern"]}
        for s in sources:
            row[s] = 1 if s in cl["sources"] else 0
        matrix.append(row)
        histories.setdefault(cl["pattern"], []).append(cl["cluster_id"])
    history_list = [{"pattern": p, "count": len(ids), "cluster_ids": ids}
                    for p, ids in sorted(histories.items(),
                                         key=lambda kv: (-len(kv[1]), kv[0]))]

    within_source_dup = sum(c["n_member_records"] - len(c["sources"])
                            for c in clusters if c["n_member_records"] > len(c["sources"]))
    fuzzy_linked = [c["cluster_id"] for c in clusters
                    if c["fuzzy_only_cross_source_link"]]

    capture_histories = {
        "case_id": case.get("case_id"),
        "skill_name": SKILL_NAME,
        "sources": sources,
        "n_raw_records": len(all_records),
        "n_clusters": len(clusters),
        "histories": history_list,
        "matrix": matrix,
        "notes": sorted(notes),
        "auxiliary_files": sorted(aux_files, key=lambda d: d["file"]),
        "material_files": sorted(used_files, key=lambda d: d["file"]),
        "identity_resolution": {
            "keys": ["doi_exact", "pmid_exact", "norm_title+year+first_author_surname"],
            "match_stats": match_stats,
            "within_source_duplicate_records": within_source_dup,
            "fuzzy_only_cross_source_clusters": fuzzy_linked,
        },
    }
    clusters_doc = {
        "case_id": case.get("case_id"),
        "sources": sources,
        "clusters": clusters,
    }
    os.makedirs(args.work, exist_ok=True)
    write_json(os.path.join(args.work, "capture_histories.json"), capture_histories)
    write_json(os.path.join(args.work, "clusters.json"), clusters_doc)
    sys.stdout.write("parse: %d 原始记录 → %d 簇，来源=%s\n"
                     % (len(all_records), len(clusters), ",".join(sources)))
    return 0


# ---------------------------------------------------------------------------
# 子命令：estimate
# ---------------------------------------------------------------------------


def build_estimate(capture_histories, truth=None):
    census = compute_census(capture_histories)
    sources = census["sources"]
    ss_reasons = small_sample_check(census)
    descriptive_only = bool(ss_reasons)

    matrix = capture_histories["matrix"]
    idres = capture_histories.get("identity_resolution", {})

    # 每库独有贡献（仅该库检出的单例簇）
    singletons = {s: 0 for s in sources}
    for row in matrix:
        on = [s for s in sources if row[s] == 1]
        if len(on) == 1:
            singletons[on[0]] += 1

    # 条件覆盖 P(在 j | 在 i)
    cond = {}
    for si in sources:
        cond[si] = {}
        for sj in sources:
            if si == sj:
                cond[si][sj] = None
            else:
                key = "%s|%s" % tuple(sorted([si, sj], key=sources.index))
                num = census["m_ij"][key]
                cond[si][sj] = r4(num / census["n_i"][si]) if census["n_i"][si] else None

    per_source = []
    for s in sources:
        per_source.append({
            "source": s,
            "detections": census["n_i"][s],
            "unique_singletons": singletons[s],
            "share_of_S_obs": r4(census["n_i"][s] / census["S_obs"])
            if census["S_obs"] else None,
        })

    # 异质性警示
    warnings = []
    total = census["S_obs"] or 1
    top = max(capture_histories["histories"], key=lambda h: h["count"], default=None)
    if top and top["count"] / total >= 0.7:
        warnings.append(
            "捕获历史高度集中：模式 %s 占 %d/%d (%.1f%%)，重叠信息稀薄，"
            "估计对假设敏感" % (top["pattern"], top["count"], census["S_obs"],
                                100.0 * top["count"] / total))
    if idres.get("fuzzy_only_cross_source_clusters"):
        warnings.append(
            "存在仅由模糊键（标题+年份+第一作者姓）连接的跨源簇: %s；"
            "若归并错误，重叠被高估、未检出被低估"
            % ",".join(idres["fuzzy_only_cross_source_clusters"]))

    # 成对 Chapman
    pairwise = []
    for a in range(len(sources)):
        for b in range(a + 1, len(sources)):
            sa, sb = sources[a], sources[b]
            m = census["m_ij"]["%s|%s" % (sa, sb)]
            est = chapman_pair(census["n_i"][sa], census["n_i"][sb], m)
            entry = {"pair": [sa, sb], "n_i": census["n_i"][sa],
                     "n_j": census["n_i"][sb], "m_ij": m}
            entry.update(est)
            if descriptive_only and est["status"] == "ok":
                entry["status"] = "suppressed_descriptive_only"
                entry["N_hat"] = None
                entry["ci95"] = None
            pairwise.append(entry)

    # Chao1
    chao = chao1_estimate(census["S_obs"], census["f1"], census["f2"])
    if descriptive_only:
        chao["status"] = "suppressed_descriptive_only"
        chao["N_hat"] = None
        chao["ci95"] = None
        chao["unseen_estimate"] = None
        chao["unseen_ci95"] = None
    else:
        chao["status"] = "ok"

    # 估计量一致性检查（Chao1 vs 最大成对 Chapman）
    ok_pairs = [p for p in pairwise if p.get("N_hat") is not None]
    if ok_pairs and chao.get("N_hat") is not None:
        ref = max(p["N_hat"] for p in ok_pairs)
        if ref > 0 and abs(chao["N_hat"] - ref) / ref > 0.5:
            warnings.append(
                "估计量分歧：Chao1=%.4f 与最大成对 Chapman=%.4f 相对差 >50%%，"
                "等可捕获性假设可能不成立，建议只报告观测重叠事实"
                % (chao["N_hat"], ref))

    # 追加来源的预期独有产出（f1 加权）
    stopping = None
    if not descriptive_only and census["S_obs"] > 0:
        singleton_rate = census["f1"] / census["S_obs"]
        mean_ni = sum(census["n_i"].values()) / len(sources) if sources else 0.0
        expected_new = singleton_rate * mean_ni
        stopping = {
            "singleton_rate": r4(singleton_rate),
            "mean_per_source_detections": r4(mean_ni),
            "expected_unique_yield_of_similar_source": r4(expected_new),
            "capped_by_unseen_ci95_upper": chao.get("unseen_ci95", [None, None])[1],
            "interpretation": "新增一个检出强度与现有库相近的来源，其独有贡献预期 "
                              "约 %.4f 条；在封闭总体与 Chao1 下界假设下，任何新来源"
                              "的独有新增以未检出估计的 95%% CI 上界 %.4f 条为参考上限"
                              % (r4(expected_new) or 0.0,
                                 (chao.get("unseen_ci95") or [None, None])[1] or 0.0),
        }

    estimate = {
        "case_id": capture_histories.get("case_id"),
        "skill_name": SKILL_NAME,
        "method": "capture-recapture: 成对 Chapman(1951) + 多源 Chao1(Chao 1987)",
        "descriptive_only": descriptive_only,
        "small_sample": {"flag": descriptive_only, "reasons": ss_reasons},
        "formula_inputs": census,
        "per_source": per_source,
        "conditional_coverage": cond,
        "pairwise_chapman": pairwise,
        "chao1": chao,
        "stopping_rule_numbers": stopping,
        "heterogeneity_warnings": warnings,
        "assumptions": ASSUMPTIONS,
        "honesty_notes": [
            "点估计 ≠ 真实总数；S_obs/f1/f2 等观测事实必须与估计成对呈现",
            "Chao1 为下界估计：真实未检出数可能高于 unseen_estimate",
            "m_ij=0 的库对 Chapman 无定义，已如实标注",
            "仅由模糊键连接的跨源簇若归并错误会系统性低估未检出数",
        ],
    }
    if truth is not None:
        estimate["truth_comparison"] = compare_truth(estimate, truth)
    return estimate


def compare_truth(estimate, truth):
    """仅合成示例可用：把估计与已知真值对比。真实案例没有真值文件。"""
    out = {"_synthetic_only": True,
           "warning": "真实案例不存在真值文件；本对比仅用于合成示例的验证演示"}
    true_total = truth.get("true_total_distinct_papers")
    if true_total is None:
        out["status"] = "truth_file_missing_total"
        return out
    out["true_total_distinct_papers"] = true_total
    out["true_unseen"] = truth.get("true_unseen")
    chao = estimate.get("chao1") or {}
    if chao.get("N_hat") is not None:
        out["chao1_N_hat"] = chao["N_hat"]
        out["chao1_error"] = r4(chao["N_hat"] - true_total)
        out["chao1_abs_error"] = r4(abs(chao["N_hat"] - true_total))
        ci = chao.get("ci95") or []
        out["true_total_within_chao1_ci95"] = \
            bool(len(ci) == 2 and ci[0] <= true_total <= ci[1])
    if chao.get("unseen_estimate") is not None and truth.get("true_unseen") is not None:
        out["unseen_estimate"] = chao["unseen_estimate"]
        out["unseen_error"] = r4(chao["unseen_estimate"] - truth["true_unseen"])
    ok_pairs = [p for p in estimate.get("pairwise_chapman", [])
                if p.get("N_hat") is not None]
    out["pairwise_chapman_vs_truth"] = [
        {"pair": p["pair"], "N_hat": p["N_hat"],
         "error": r4(p["N_hat"] - true_total)} for p in ok_pairs]
    return out


def cmd_estimate(args):
    ch_path = os.path.join(args.work, "capture_histories.json")
    if not os.path.isfile(ch_path):
        sys.stderr.write("ERROR: 缺少 %s（请先运行 parse）\n" % ch_path)
        return 3
    capture_histories = read_json(ch_path)
    truth = None
    if args.truth:
        if not os.path.isfile(args.truth):
            sys.stderr.write("ERROR: truth 文件不存在: %s\n" % args.truth)
            return 3
        truth = read_json(args.truth)
    estimate = build_estimate(capture_histories, truth=truth)
    os.makedirs(args.output, exist_ok=True)
    write_json(os.path.join(args.output, "recall_estimate.json"), estimate)
    sys.stdout.write("estimate: descriptive_only=%s\n" % estimate["descriptive_only"])
    return 0


# ---------------------------------------------------------------------------
# 子命令：report
# ---------------------------------------------------------------------------


def fmt(x, nd=4):
    if x is None:
        return "—"
    if isinstance(x, float):
        return ("%%.%df" % nd) % x
    return str(x)


def cmd_report(args):
    ch_path = os.path.join(args.work, "capture_histories.json")
    est_path = os.path.join(args.output, "recall_estimate.json")
    for p in (ch_path, est_path):
        if not os.path.isfile(p):
            sys.stderr.write("ERROR: 缺少 %s（请先运行 parse/estimate）\n" % p)
            return 3
    ch = read_json(ch_path)
    est = read_json(est_path)
    census = est["formula_inputs"]
    sources = census["sources"]

    L = []
    L.append("# 召回统计估计报告（capture–recapture）")
    L.append("")
    L.append("- case_id: `%s`" % est.get("case_id"))
    L.append("- 方法: %s" % est["method"])
    L.append("- 数据来源: %s" % "、".join(sources))
    L.append("- 原始记录数: **%d**；身份归并后簇数 S_obs: **%d**"
             % (ch["n_raw_records"], census["S_obs"]))
    if est["descriptive_only"]:
        L.append("- ⚠️ **小样本降级（descriptive-only）**：%s。本报告只给出观测"
                 "重叠事实，不给出点估计。" % "；".join(
                     est["small_sample"]["reasons"]))
    L.append("")
    L.append("> 所有数字均可追溯至 `capture_histories.json`（观测事实）或由 "
             "`references/estimators.md` 中声明的公式直接计算（估计值）。")
    L.append("")

    L.append("## 1. 捕获历史普查（overlap census）")
    L.append("")
    L.append("捕获历史为簇 × 来源的 0/1 模式，位序 = [%s]。"
             % ", ".join(sources))
    L.append("")
    L.append("| 捕获历史模式 | 簇数 | 簇 ID |")
    L.append("|---|---|---|")
    for h in ch["histories"]:
        L.append("| `%s` | %d | %s |"
                 % (h["pattern"], h["count"], ", ".join(h["cluster_ids"])))
    L.append("")
    L.append("关键频数：f1（恰被 1 个库检出的簇）= **%d**；f2（恰被 2 个库检出的簇）"
             "= **%d**；S_obs = **%d**。" % (census["f1"], census["f2"],
                                              census["S_obs"]))
    L.append("")

    L.append("## 2. 各库检出与独有贡献")
    L.append("")
    L.append("| 来源 | 检出簇数 n_i | 独有单例簇 | 占 S_obs 比例 |")
    L.append("|---|---|---|---|")
    for ps in est["per_source"]:
        L.append("| %s | %d | %d | %s |"
                 % (ps["source"], ps["detections"], ps["unique_singletons"],
                    fmt(ps["share_of_S_obs"])))
    L.append("")

    L.append("## 3. 条件覆盖矩阵 P(在列库 | 在行库)")
    L.append("")
    header = "| 行 \\ 列 |" + "|".join(sources) + "|"
    L.append(header)
    L.append("|" + "---|" * (len(sources) + 1))
    for si in sources:
        cells = [fmt(est["conditional_coverage"][si][sj], 4) for sj in sources]
        L.append("| %s |%s|" % (si, "|".join(cells)))
    L.append("")
    L.append("每格 = m_ij / n_i（均由捕获历史矩阵直接计数得到）。")
    L.append("")

    L.append("## 4. 成对 Chapman 估计（Lincoln–Petersen 偏差校正版）")
    L.append("")
    L.append("N̂ = ((n_i+1)(n_j+1)/(m_ij+1)) − 1；95% CI 为正态近似 "
             "N̂ ± 1.96·SE，下界不低于 max(n_i, n_j)。")
    L.append("")
    L.append("| 库对 | n_i | n_j | m_ij | N̂ | SE | 95% CI | 状态 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for p in est["pairwise_chapman"]:
        ci = p.get("ci95")
        ci_s = "[%s, %s]" % (fmt(ci[0]), fmt(ci[1])) if ci else "—"
        L.append("| %s × %s | %d | %d | %d | %s | %s | %s | %s |"
                 % (p["pair"][0], p["pair"][1], p["n_i"], p["n_j"], p["m_ij"],
                    fmt(p.get("N_hat")), fmt(p.get("se")), ci_s, p["status"]))
    L.append("")
    for p in est["pairwise_chapman"]:
        if p["status"] == "undefined_zero_overlap":
            L.append("- ⚠️ 库对 %s × %s 的 m_ij=0，Chapman 估计无定义，已如实标注。"
                     % (p["pair"][0], p["pair"][1]))
    L.append("")

    L.append("## 5. 多源 Chao1 下界估计")
    L.append("")
    chao = est["chao1"]
    if est["descriptive_only"]:
        L.append("**descriptive-only 降级**：不给出点估计。观测事实：S_obs=%d, "
                 "f1=%d, f2=%d。" % (census["S_obs"], census["f1"], census["f2"]))
    else:
        L.append("- 变体: `%s`（f2>0 用经典式 S_obs + f1²/(2f2)；f2=0 用偏差校正式 "
                 "f1(f1−1)/2）" % chao["variant"])
        L.append("- 公式输入: S_obs=%d, f1=%d, f2=%d"
                 % (census["S_obs"], census["f1"], census["f2"]))
        L.append("- **N̂(Chao1) = %s**；方差 = %s"
                 % (fmt(chao.get("N_hat")), fmt(chao.get("variance"))))
        L.append("- 对数变换 95%% CI = **[%s, %s]**（C 因子 = %s）"
                 % (fmt((chao.get("ci95") or [None])[0]),
                    fmt((chao.get("ci95") or [None, None])[1]),
                    fmt(chao.get("log_ci_factor"))))
        L.append("- 未检出估计 unseen = max(0, N̂ − S_obs) = **%s**，"
                 "95%% CI = **[%s, %s]**"
                 % (fmt(chao.get("unseen_estimate")),
                    fmt((chao.get("unseen_ci95") or [None])[0]),
                    fmt((chao.get("unseen_ci95") or [None, None])[1])))
        L.append("")
        L.append("> 读法：在假设成立时，三个库合计可能漏检约 %s 条（95%% CI [%s, %s]）。"
                 "Chao1 是**下界**估计，真实遗漏可能更多；它不等于真实总数。"
                 % (fmt(chao.get("unseen_estimate")),
                    fmt((chao.get("unseen_ci95") or [None])[0]),
                    fmt((chao.get("unseen_ci95") or [None, None])[1])))
    L.append("")

    L.append("## 6. 停止规则 / 追加来源的预期产出")
    L.append("")
    st = est.get("stopping_rule_numbers")
    if st:
        L.append("- 单例率 f1/S_obs = %s；各库平均检出 = %s"
                 % (fmt(st["singleton_rate"]), fmt(st["mean_per_source_detections"])))
        L.append("- %s" % st["interpretation"])
    else:
        L.append("descriptive-only 降级，不计算追加来源预期产出。")
    L.append("")

    if est.get("heterogeneity_warnings"):
        L.append("## 7. 异质性与归并警示")
        L.append("")
        for w in est["heterogeneity_warnings"]:
            L.append("- ⚠️ %s" % w)
        L.append("")

    if est.get("truth_comparison"):
        tc = est["truth_comparison"]
        L.append("## 8. 合成真值对照（仅合成示例）")
        L.append("")
        L.append("> %s" % tc.get("warning", ""))
        L.append("")
        L.append("- 真实不同文献总数 = %s；真实未捕获 = %s"
                 % (fmt(tc.get("true_total_distinct_papers")),
                    fmt(tc.get("true_unseen"))))
        if "chao1_N_hat" in tc:
            L.append("- Chao1 N̂ = %s，误差 = %s；真值落在 95%% CI 内: %s"
                     % (fmt(tc.get("chao1_N_hat")), fmt(tc.get("chao1_error")),
                        "是" if tc.get("true_total_within_chao1_ci95") else "否"))
        if "unseen_error" in tc:
            L.append("- 未检出估计 = %s，误差 = %s"
                     % (fmt(tc.get("unseen_estimate")), fmt(tc.get("unseen_error"))))
        for row in tc.get("pairwise_chapman_vs_truth", []):
            L.append("- Chapman(%s × %s) N̂ = %s，误差 = %s"
                     % (row["pair"][0], row["pair"][1],
                        fmt(row["N_hat"]), fmt(row["error"])))
        L.append("")

    L.append("## 局限性")
    L.append("")
    for a in est["assumptions"]:
        L.append("- %s" % a)
    for h in est.get("honesty_notes", []):
        L.append("- %s" % h)
    L.append("")
    L.append("---")
    L.append("本报告由 %s 自动生成；若 Agent 改写了遗漏陈述，改写记录见 "
             "result.json 的 change_records。" % SKILL_NAME)
    L.append("")
    text = "\n".join(L)
    write_text(os.path.join(args.output, "recall_report.md"), text)
    # 供 finalize 使用的基线遗漏陈述
    omission = build_omission_statement(est)
    write_text(os.path.join(args.work, "omission_statement_baseline.md"), omission)
    sys.stdout.write("report: recall_report.md 写出（%d 行）\n" % len(L))
    return 0


def build_omission_statement(est):
    """由数字模板生成的确定性基线遗漏陈述（Agent 可改写并登记）。"""
    census = est["formula_inputs"]
    chao = est["chao1"]
    if est["descriptive_only"]:
        return (
            "小样本降级（%s）：仅报告观测事实——%d 个来源共检出 %d 个去重簇，"
            "f1=%d，f2=%d；样本量不足以支持统计估计，不能给出未检出数的点估计，"
            "遗漏情况无法量化，建议扩充检索来源后重新评估。"
            % ("；".join(est["small_sample"]["reasons"]),
               len(census["sources"]), census["S_obs"],
               census["f1"], census["f2"]))
    st = est.get("stopping_rule_numbers") or {}
    return (
        "基于 %d 个来源的捕获-再捕获分析：去重后共观测到 S_obs=%d 条相关记录"
        "（f1=%d，f2=%d）。Chao1 下界估计总相关数 N̂=%s（95%% CI [%s, %s]），"
        "即估计约 %s 条未被任何来源检出（95%% CI [%s, %s]；点估计≠真实总数，"
        "Chao1 为下界）。%s。若假设（封闭总体、重叠结构含信息、无行为响应、"
        "归并正确）不成立，以上数字失效，只有观测重叠事实有效。"
        % (len(census["sources"]), census["S_obs"], census["f1"], census["f2"],
           fmt(chao.get("N_hat")), fmt((chao.get("ci95") or [None])[0]),
           fmt((chao.get("ci95") or [None, None])[1]),
           fmt(chao.get("unseen_estimate")),
           fmt((chao.get("unseen_ci95") or [None])[0]),
           fmt((chao.get("unseen_ci95") or [None, None])[1]),
           st.get("interpretation", "")))


# ---------------------------------------------------------------------------
# 子命令：finalize
# ---------------------------------------------------------------------------


def fill_contract_field(name, shape, ctx):
    """按契约字段名/形状填充；填不出返回 (None, False)。"""
    lname = name.lower()
    est = ctx["estimate"]
    census = est["formula_inputs"] if est else None
    if "candidate" in lname:
        return ctx["candidates"], True
    if "recall" in lname or "estimate" in lname or "unseen" in lname:
        if not est:
            return None, False
        chao = est.get("chao1") or {}
        return {
            "S_obs": census["S_obs"], "f1": census["f1"], "f2": census["f2"],
            "descriptive_only": est["descriptive_only"],
            "chao1_N_hat": chao.get("N_hat"),
            "chao1_ci95": chao.get("ci95"),
            "unseen_estimate": chao.get("unseen_estimate"),
            "unseen_ci95": chao.get("unseen_ci95"),
        }, True
    if "omission" in lname or "stopping" in lname:
        return ctx["omission_statement"], True
    if "uncertainty" in lname:
        return ctx["uncertainty_statement"], True
    if "change" in lname:
        return ctx["change_records"], True
    if "source" in lname and shape == "list":
        return [s["file"] for s in ctx["sources_meta"]], True
    if "summary" in lname and est:
        return {"counts": ctx["counts"],
                "descriptive_only": est["descriptive_only"]}, True
    return None, False


def cmd_finalize(args):
    case_path = args.case or os.path.join(args.input, "case.json")
    if not os.path.isfile(case_path):
        sys.stderr.write("ERROR: case.json 不存在: %s\n" % case_path)
        return 3
    try:
        case = read_json(case_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("ERROR: case.json 不可解析: %s\n" % exc)
        return 3

    ch_path = os.path.join(args.work, "capture_histories.json")
    est_path = os.path.join(args.output, "recall_estimate.json")
    if not os.path.isfile(ch_path) or not os.path.isfile(est_path):
        sys.stderr.write("ERROR: 缺少中间产物（请先运行 parse/estimate）\n")
        return 3
    ch = read_json(ch_path)
    est = read_json(est_path)
    census = est["formula_inputs"]

    clusters = read_json(os.path.join(args.work, "clusters.json"))["clusters"]
    candidates = [{
        "cluster_id": c["cluster_id"],
        "pattern": c["pattern"],
        "sources": c["sources"],
        "representative": c["representative"],
    } for c in clusters]

    # 遗漏陈述：优先采用 Agent 改写版（work/omission_statement.md）
    change_records = []
    baseline_path = os.path.join(args.work, "omission_statement_baseline.md")
    override_path = os.path.join(args.work, "omission_statement.md")
    if os.path.isfile(override_path):
        with open(override_path, "r", encoding="utf-8") as f:
            omission = f.read().strip()
        change_records.append({
            "field": "omission_statement",
            "action": "model_authored_override",
            "detail": "Agent 在脚本基线之上改写了遗漏陈述（必须引用 recall_estimate.json "
                      "中的数字）；基线见 work/omission_statement_baseline.md",
        })
    elif os.path.isfile(baseline_path):
        with open(baseline_path, "r", encoding="utf-8") as f:
            omission = f.read().strip()
        change_records.append({
            "field": "omission_statement",
            "action": "script_baseline",
            "detail": "遗漏陈述由脚本数字模板生成（确定性，未经 Agent 改写）",
        })
    else:
        omission = None

    idres = ch.get("identity_resolution", {})
    fuzzy_links = idres.get("fuzzy_only_cross_source_clusters", [])
    uncertainty = []
    uncertainty.append("点估计≠真实总数：Chao1 为下界估计，真实未检出数可能更高")
    uncertainty.append("封闭总体假设风险：材料快照期间总体若变动，估计失效")
    uncertainty.append("等可捕获性风险：来源档案画像差异大（广谱索引 vs 利基出版商）时，"
                       "重叠结构可能不含足够信息，此时只有观测事实有效")
    for w in est.get("heterogeneity_warnings", []):
        uncertainty.append(w)
    if fuzzy_links:
        uncertainty.append("不可验证身份：簇 %s 仅靠 标题+年份+第一作者姓 模糊键跨源连接，"
                           "若归并错误则未检出数被低估" % ",".join(fuzzy_links))
    if est["descriptive_only"]:
        uncertainty.append("小样本警示：%s；所有点估计被抑制，只有描述性事实有效"
                           % "；".join(est["small_sample"]["reasons"]))
    for p in est.get("pairwise_chapman", []):
        if p["status"] == "undefined_zero_overlap":
            uncertainty.append("库对 %s × %s 零重叠，Chapman 无定义"
                               % (p["pair"][0], p["pair"][1]))
    uncertainty_statement = "；".join(uncertainty)

    # 来源文件 sha256
    sources_meta = []
    for mf in ch.get("material_files", []):
        for cand in (os.path.join(args.input, mf["file"]),
                     os.path.join(args.input, "materials", mf["file"])):
            if os.path.isfile(cand):
                sources_meta.append({
                    "file": mf["file"], "kind": mf["kind"],
                    "source": mf["source"], "records": mf["records"],
                    "sha256": sha256_file(cand)})
                break
    for af in ch.get("auxiliary_files", []):
        for cand in (os.path.join(args.input, af["file"]),
                     os.path.join(args.input, "materials", af["file"])):
            if os.path.isfile(cand):
                sources_meta.append({
                    "file": af["file"], "kind": af["kind"], "source": None,
                    "records": None, "sha256": sha256_file(cand)})
                break

    counts = {
        "records": ch["n_raw_records"],
        "clusters": census["S_obs"],
        "sources": len(census["sources"]),
        "per_source_detections": census["n_i"],
        "f1": census["f1"],
        "f2": census["f2"],
        "unseen_point_estimate": (est.get("chao1") or {}).get("unseen_estimate"),
    }

    ctx = {"estimate": est, "candidates": candidates,
           "omission_statement": omission,
           "uncertainty_statement": uncertainty_statement,
           "change_records": change_records,
           "sources_meta": sources_meta, "counts": counts}

    result = {
        "case_id": case.get("case_id"),
        "skill_name": SKILL_NAME,
        "status": "complete",
        "products": {
            "capture_histories": "capture_histories.json",
            "clusters": "clusters.json",
            "recall_estimate": "recall_estimate.json",
            "recall_report": "recall_report.md",
        },
        "sources": sources_meta,
        "uncertainty": uncertainty,
        "change_records": change_records,
        "counts": counts,
        "checks": {"selfcheck": "not_run"},
        "unresolved_contract_fields": [],
    }

    # 填充 output_contract
    contract = case.get("output_contract") or {}
    for field, shape in contract.items():
        value, ok = fill_contract_field(field, shape, ctx)
        if ok:
            result[field] = value
        else:
            result[field] = None
            result["unresolved_contract_fields"].append(
                {"field": field, "declared_shape": shape,
                 "reason": "无可靠填充来源，如实置 null"})
    if result["unresolved_contract_fields"]:
        result["status"] = "partial"
    elif est["descriptive_only"] \
            or any(p["status"] == "undefined_zero_overlap"
                   for p in est.get("pairwise_chapman", [])):
        # 分析性降级：小样本或存在零重叠库对 ⇒ 结论须以观测事实为准
        result["status"] = "partial"

    # 真值对照摘要（仅合成示例存在）
    if est.get("truth_comparison"):
        tc = est["truth_comparison"]
        result["truth_comparison_summary"] = {
            "synthetic_only": True,
            "true_total_distinct_papers": tc.get("true_total_distinct_papers"),
            "chao1_N_hat": tc.get("chao1_N_hat"),
            "chao1_abs_error": tc.get("chao1_abs_error"),
            "true_total_within_chao1_ci95":
                tc.get("true_total_within_chao1_ci95"),
            "detail": "recall_estimate.json#truth_comparison",
        }

    # 复制中间产物到 output
    os.makedirs(args.output, exist_ok=True)
    write_json(os.path.join(args.output, "capture_histories.json"), ch)
    write_json(os.path.join(args.output, "clusters.json"),
               read_json(os.path.join(args.work, "clusters.json")))
    write_json(os.path.join(args.output, "result.json"), result)
    sys.stdout.write("finalize: status=%s unresolved=%d\n"
                     % (result["status"],
                        len(result["unresolved_contract_fields"])))
    return 2 if result["unresolved_contract_fields"] else 0


# ---------------------------------------------------------------------------
# 子命令：selfcheck
# ---------------------------------------------------------------------------


def selfcheck(work, output):
    problems = []
    ch_path = os.path.join(output, "capture_histories.json")
    est_path = os.path.join(output, "recall_estimate.json")
    res_path = os.path.join(output, "result.json")
    for p in (ch_path, est_path, res_path):
        if not os.path.isfile(p):
            problems.append("缺少产物: %s" % os.path.basename(p))
    if problems:
        return problems
    ch = read_json(ch_path)
    est = read_json(est_path)
    res = read_json(res_path)

    # 1. result.json 契约键
    case_id = res.get("case_id")
    if not case_id:
        problems.append("result.json 缺少 case_id")
    for f in res.get("unresolved_contract_fields", []):
        fname = f["field"]
        if fname not in res:
            problems.append("unresolved 字段 %s 未以 null 出现在 result.json" % fname)

    # 2. 公式输入重算
    census = compute_census(ch)
    fi = est.get("formula_inputs", {})
    for key in ("S_obs", "f1", "f2"):
        if fi.get(key) != census[key]:
            problems.append("formula_inputs.%s=%s 与重算值 %s 不一致"
                            % (key, fi.get(key), census[key]))
    if fi.get("n_i") != census["n_i"]:
        problems.append("formula_inputs.n_i 与重算值不一致: %s vs %s"
                        % (fi.get("n_i"), census["n_i"]))
    if fi.get("m_ij") != census["m_ij"]:
        problems.append("formula_inputs.m_ij 与重算值不一致: %s vs %s"
                        % (fi.get("m_ij"), census["m_ij"]))

    # 3. 估计值重算（若非 descriptive_only）
    if not est.get("descriptive_only"):
        chao = est.get("chao1", {})
        re = chao1_estimate(census["S_obs"], census["f1"], census["f2"])
        for key in ("N_hat", "variance", "ci95", "unseen_estimate", "unseen_ci95"):
            if chao.get(key) != re.get(key):
                problems.append("chao1.%s=%s 与公式重算值 %s 不一致"
                                % (key, chao.get(key), re.get(key)))
        for p in est.get("pairwise_chapman", []):
            sa, sb = p["pair"]
            m = census["m_ij"]["%s|%s" % (sa, sb)]
            re_p = chapman_pair(census["n_i"][sa], census["n_i"][sb], m)
            if re_p["status"] == "ok":
                for key in ("N_hat", "variance", "se", "ci95"):
                    if p.get(key) != re_p.get(key):
                        problems.append("Chapman %s×%s.%s=%s 与重算值 %s 不一致"
                                        % (sa, sb, key, p.get(key), re_p.get(key)))
            elif p.get("status") not in ("undefined_zero_overlap",
                                         "suppressed_descriptive_only"):
                problems.append("Chapman %s×%s 状态异常: %s" % (sa, sb, p.get("status")))

    # 4. CI 一致性：lower ≤ point ≤ upper（或被显式抑制）
    def check_ci(name, point, ci):
        if point is None or ci is None:
            return
        if not (ci[0] <= point <= ci[1]):
            problems.append("%s: CI [%s, %s] 不含点估计 %s"
                            % (name, ci[0], ci[1], point))
    chao = est.get("chao1", {})
    check_ci("chao1", chao.get("N_hat"), chao.get("ci95"))
    for p in est.get("pairwise_chapman", []):
        check_ci("chapman %s×%s" % tuple(p["pair"]), p.get("N_hat"), p.get("ci95"))

    # 5. 成员矩阵行和 == 模式位 1 的个数
    for row in ch["matrix"]:
        s = sum(row[src] for src in ch["sources"])
        if s != row["pattern"].count("1"):
            problems.append("矩阵行 %s 行和 %d ≠ 模式 %s 的位数"
                            % (row["cluster_id"], s, row["pattern"]))
    # 6. 历史计数与矩阵一致
    hist_total = sum(h["count"] for h in ch["histories"])
    if hist_total != len(ch["matrix"]):
        problems.append("histories 计数之和 %d ≠ 矩阵行数 %d"
                        % (hist_total, len(ch["matrix"])))
    # 7. counts 一致性
    if res.get("counts", {}).get("clusters") != census["S_obs"]:
        problems.append("result.counts.clusters 与 S_obs 不一致")
    return problems


def cmd_selfcheck(args):
    problems = selfcheck(args.work, args.output)
    if problems:
        for p in problems:
            sys.stdout.write("FAIL: %s\n" % p)
        # 把自查结论写回 result.json（若存在）
        res_path = os.path.join(args.output, "result.json")
        if os.path.isfile(res_path):
            res = read_json(res_path)
            res.setdefault("checks", {})["selfcheck"] = "failed: " + "; ".join(problems)
            write_json(res_path, res)
        return 1
    res_path = os.path.join(args.output, "result.json")
    if os.path.isfile(res_path):
        res = read_json(res_path)
        res.setdefault("checks", {})["selfcheck"] = "passed"
        write_json(res_path, res)
    sys.stdout.write("selfcheck: 全部通过\n")
    return 0


# ---------------------------------------------------------------------------
# 子命令：run-all
# ---------------------------------------------------------------------------


def cmd_run_all(args):
    case_path = os.path.join(args.input, "case.json")
    if not os.path.isfile(case_path):
        # 输入无效：在 output 写最小诚实 result.json，退出 3
        try:
            os.makedirs(args.output, exist_ok=True)
            write_json(os.path.join(args.output, "result.json"), {
                "case_id": None, "skill_name": SKILL_NAME, "status": "failed",
                "error": "case.json 不存在: %s" % case_path,
                "unresolved_contract_fields": [],
            })
        except OSError:
            pass
        sys.stderr.write("ERROR: case.json 不存在: %s\n" % case_path)
        return 3
    ns = argparse.Namespace(input=args.input, work=args.work, output=args.output,
                            case=None, truth=args.truth)
    try:
        rc = cmd_parse(ns)
        if rc != 0:
            return rc
        rc = cmd_estimate(ns)
        if rc != 0:
            return rc
        rc = cmd_report(ns)
        if rc != 0:
            return rc
        rc = cmd_finalize(ns)
        finalize_rc = rc
        sc = cmd_selfcheck(ns)
        if sc != 0:
            return 2
        return finalize_rc
    except Exception as exc:  # 诚实降级：不崩溃、不静默
        try:
            os.makedirs(args.output, exist_ok=True)
            write_json(os.path.join(args.output, "result.json"), {
                "case_id": None, "skill_name": SKILL_NAME, "status": "failed",
                "error": "顶层异常: %s: %s" % (type(exc).__name__, exc),
                "unresolved_contract_fields": [],
            })
        except OSError:
            pass
        sys.stderr.write("DEGRADED: %s: %s\n" % (type(exc).__name__, exc))
        return 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(
        prog="recall_estimator.py",
        description="多数据库联合检索的召回统计估计（capture–recapture："
                    "Chapman 两库 / Chao1 多库 + 置信区间 + 停止规则）。"
                    "纯标准库、离线、确定性。")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp, need_input=False, need_truth=False):
        if need_input:
            sp.add_argument("--input", default="/input", help="输入目录（含 case.json 与材料）")
        sp.add_argument("--work", default="/app/work", help="中间产物目录")
        sp.add_argument("--output", default="/app/output", help="最终产物目录")
        sp.add_argument("--case", default=None, help="case.json 路径（默认 <input>/case.json）")
        if need_truth:
            sp.add_argument("--truth", default=None,
                            help="【仅合成示例】已知真值 JSON，用于估计-真值对照")

    add_common(sub.add_parser("parse", help="嗅探+规范化+最小身份归并，写 capture_histories.json/clusters.json"),
               need_input=True)
    add_common(sub.add_parser("estimate", help="由捕获历史计算 Chapman/Chao1/CI/贡献表"),
               need_truth=True)
    add_common(sub.add_parser("report", help="生成 recall_report.md（所有数字可追溯）"))
    add_common(sub.add_parser("finalize", help="生成 result.json（含契约字段与诚实声明）"),
               need_input=True)
    add_common(sub.add_parser("selfcheck", help="契约/公式重算/CI/矩阵一致性自查，exit 0/1"))
    sp = sub.add_parser("run-all", help="parse→estimate→report→finalize→selfcheck 一条龙（诚实降级）")
    add_common(sp, need_input=True, need_truth=True)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "parse":
        return cmd_parse(args)
    if args.command == "estimate":
        return cmd_estimate(args)
    if args.command == "report":
        return cmd_report(args)
    if args.command == "finalize":
        return cmd_finalize(args)
    if args.command == "selfcheck":
        return cmd_selfcheck(args)
    if args.command == "run-all":
        return cmd_run_all(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
