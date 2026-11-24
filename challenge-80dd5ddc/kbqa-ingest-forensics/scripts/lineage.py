#!/usr/bin/env python3
"""lineage.py — 别名/版本谱系判定（bundle 1，确定性，stdlib-only）。

在 forensic_scan.py 的 catalog.json 之上判定文件间关系：
  byte_duplicate  同一 SHA-256（已在扫描阶段标注）
  alias           内容几乎相同（5-gram shingle Jaccard ≥ 0.85）但文件名/路径不同
  revision_chain  同一文档的不同版本（同词干，或 Jaccard ≥ 0.60，
                  或同词干且公共 shingle ≥ 10 且 Jaccard ≥ 0.35）
版本排序优先级：行政版本备注（库内 *说明*/notes/readme 类文件明确指认）>
文件名版本标记（v1/v2/final/日期）> mtime。每条判定都携带机器依据，
写入 lineage.json；行政备注原文行号同时记录，供复核。
"""
import argparse
import json
import os
import re
import sys
import time

ADMIN_HINT = ("说明", "备注", "notes", "note", "readme", "版本", "version", "manifest", "索引")
VER_PAT = re.compile(r"(?i)(?:^|[_\-\s\((])v?(\d+(?:\.\d+)*)|final|final(\d*)|最新|旧版|草稿|draft|(20\d{2})[-_.年]?(0[1-9]|1[0-2])?")
CJK_SPLIT = re.compile(r"[\s，。；：、（）()\[\]【】\-_/\\.,;:!?\"'<>|#*+=~`@$%^&]+")


def norm_stem(relpath):
    stem = os.path.splitext(os.path.basename(relpath))[0].lower()
    stem = re.sub(r"(?i)[_\-\s\(]?(v\d+(\.\d+)*|final\d*|copy|副本|复件|最新|旧版|草稿|draft|backup|bak|\(\d+\)|20\d{2}[-_.年]?\d{0,2})\)?", " ", stem)
    stem = re.sub(r"[\s_\-]+", "", stem)
    return stem


def shingles(text, n=5):
    toks = [t for t in CJK_SPLIT.split(text.lower()) if t]
    if len(toks) < n:
        return set(toks)
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def read_extracted(work, entry):
    if not entry.get("extracted"):
        return ""
    p = os.path.join(work, entry["extracted"])
    try:
        with open(p, encoding="utf-8") as f:
            return re.sub(r"^L\d+: ", "", f.read(), flags=re.M)
    except OSError:
        return ""


def parse_admin_notes(catalog, work):
    """从行政备注类文件中解析 '某文件 … 为当前/有效/最新版本' 类指认。
    返回 {norm_stem_or_name: {"current": bool, "source": "Fxx:L行", "quote": str}}"""
    claims = {}
    for e in catalog["files"]:
        name = os.path.basename(e["relpath"]).lower()
        if not any(h in name for h in ADMIN_HINT):
            continue
        text = read_extracted(work, e)
        for i, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            if not line.strip():
                continue
            is_current = any(k in line for k in ("当前", "有效", "最新", "以…为准")) or \
                any(k in low for k in ("current", "latest", "valid", "supersede"))
            is_old = any(k in line for k in ("作废", "废止", "历史", "归档", "不再使用")) or \
                any(k in low for k in ("deprecated", "obsolete", "archived", "superseded"))
            if not (is_current or is_old):
                continue
            for e2 in catalog["files"]:
                if e2["file_id"] == e["file_id"]:
                    continue
                base = os.path.basename(e2["relpath"]).lower()
                stem_full = os.path.splitext(base)[0]
                if (base and base in low) or (len(stem_full) >= 4 and stem_full in low):
                    key = e2["file_id"]
                    # 同文件多条指认：current 优先于 old
                    if key in claims and claims[key]["current"] and not is_current:
                        continue
                    claims[key] = {"current": bool(is_current and not is_old),
                                   "source": "%s:L%d" % (e["file_id"], i),
                                   "quote": line.strip()[:200]}
    return claims


def version_rank(relpath):
    """文件名版本标记 → 可比较元组（越大越新）。无法识别时返回 None。"""
    base = os.path.basename(relpath).lower()
    m = re.search(r"(?i)(?:^|[_\-\s\(])v(\d+(?:\.\d+)*)", base)
    if m:
        return (2,) + tuple(int(x) for x in m.group(1).split("."))
    if "final" in base or "最新" in base:
        return (3, 0)
    if "旧版" in base or "draft" in base or "草稿" in base:
        return (0, 0)
    m = re.search(r"(20\d{2})[-_.年]?(0[1-9]|1[0-2])?", base)
    if m:
        return (1, int(m.group(1)), int(m.group(2) or 0))
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    with open(os.path.join(a.work, "catalog.json"), encoding="utf-8") as f:
        catalog = json.load(f)
    os.makedirs(a.out, exist_ok=True)

    entries = catalog["files"]
    text_by_id = {e["file_id"]: read_extracted(a.work, e) for e in entries}
    sh_by_id = {fid: shingles(t) for fid, t in text_by_id.items() if t}
    admin = parse_admin_notes(catalog, a.work)

    # 两两相似度
    pairs = []
    ids = sorted(sh_by_id)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            A, B = sh_by_id[ids[i]], sh_by_id[ids[j]]
            if not A or not B:
                continue
            inter = len(A & B)
            if not inter:
                continue
            jac = inter / len(A | B)
            pairs.append((ids[i], ids[j], jac, inter))

    relations = []
    groups = {}  # stem -> [file_id]
    for e in entries:
        if e["text_status"] == "ok":
            groups.setdefault(norm_stem(e["relpath"]), []).append(e["file_id"])
    for h, members in ((g["sha256"], g["members"]) for g in catalog.get("byte_duplicate_groups", [])):
        for k in range(1, len(members)):
            relations.append({"type": "byte_duplicate", "a": members[0], "b": members[k],
                              "basis": "identical sha256 " + h[:12]})
    for x, y, jac, inter in pairs:
        stem_x = norm_stem(next(e["relpath"] for e in entries if e["file_id"] == x))
        stem_y = norm_stem(next(e["relpath"] for e in entries if e["file_id"] == y))
        same_stem = stem_x == stem_y and stem_x != ""
        if jac >= 0.85 and not same_stem:
            relations.append({"type": "alias", "a": x, "b": y,
                              "basis": "shingle Jaccard=%.3f≥0.85, different stems" % jac})
        if same_stem or jac >= 0.60 or (same_stem and inter >= 10 and jac >= 0.35):
            if jac < 0.995:  # 近似但不相同 → 版本链候选
                relations.append({"type": "revision_chain", "a": x, "b": y,
                                  "basis": "same_stem=%s Jaccard=%.3f common=%d" % (same_stem, jac, inter)})

    # 版本分组与排序：并集（revision_chain + byte_duplicate 连通分量）
    parent = {e["file_id"]: e["file_id"] for e in entries}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for r in relations:
        if r["type"] in ("revision_chain", "byte_duplicate"):
            union(r["a"], r["b"])
    comps = {}
    for fid in parent:
        comps.setdefault(find(fid), []).append(fid)

    by_id = {e["file_id"]: e for e in entries}
    version_groups = []
    for members in sorted(comps.values(), key=lambda ms: sorted(ms)[0]):
        if len(members) < 2:
            continue
        ranked = []
        for fid in sorted(members):
            e = by_id[fid]
            adm = admin.get(fid)
            vr = version_rank(e["relpath"])
            # 排序键：行政备注 > 文件名版本 > mtime
            key = (2 if (adm and adm["current"]) else 0,
                   vr if vr else (0,),
                   e["mtime"] or "")
            ranked.append({"file_id": fid, "relpath": e["relpath"],
                           "sha256_8": (e["sha256"] or "")[:8],
                           "admin_note": adm, "name_version": vr,
                           "mtime": e["mtime"], "_key": key})
        ranked.sort(key=lambda r: tuple(str(x) for x in r["_key"]), reverse=True)
        for k, r in enumerate(ranked):
            r["role"] = "current" if k == 0 else (
                "current_copy" if any(rel["type"] == "byte_duplicate" and
                                      {rel["a"], rel["b"]} == {ranked[0]["file_id"], r["file_id"]}
                                      for rel in relations) else "historical")
            del r["_key"]
        version_groups.append({"members": ranked})

    out = {"schema": "kbqa-ingest-forensics/lineage/v1",
           "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "relations": relations, "version_groups": version_groups,
           "admin_note_claims": admin,
           "rule": "排序优先级：行政版本备注 > 文件名版本标记 > mtime；"
                   "byte_duplicate=同SHA-256，alias=Jaccard≥0.85异名，"
                   "revision_chain=同词干或Jaccard≥0.60或(同词干且公共≥10且≥0.35)"}
    for dest in (os.path.join(a.work, "lineage.json"), os.path.join(a.out, "lineage.json")):
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({"relations": len(relations),
                      "version_groups": len(version_groups),
                      "admin_claims": len(admin)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
