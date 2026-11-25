#!/usr/bin/env python3
"""catalogforge.py - read-only catalog, search index and contract delivery
for a research document library.

Pure Python 3 standard library (3.8+). No third-party dependencies.
Never modifies the source library: every subcommand only READS the
materials and writes new artifacts under the given output paths.

Subcommands:
  catalog   Build catalog.jsonl: one record per file with stable id,
            hashes, metadata merged from sidecar files, version and
            alias edges with explicit evidence.
  index     Load catalog.jsonl into a SQLite database (FTS5 when the
            runtime provides it, LIKE fallback otherwise).
  query     Run one search against the index; every hit carries evidence
            (matched field, snippet, path, sha256). Zero-hit queries get
            an explicit recall note instead of silence.
  answer    Answer a list of questions with citations into the catalog;
            abstains with a stated reason when evidence is missing.
  contract  Assemble or audit result.json against the case's
            output_contract: case_id is copied from case.json, every
            contracted field is either filled from a real artifact or
            honestly marked not_produced.
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sqlite3
import sys

TEXT_EXTS = (".txt", ".md", ".markdown", ".json", ".jsonl", ".csv",
             ".tsv", ".yaml", ".yml", ".xml", ".html", ".htm", ".bib",
             ".ris", ".log", ".py", ".tex")
EXCERPT_CHARS = 2000

COPY_PATTERNS = [
    r"\s*\(\d+\)$", r"\s*（\d+）$",
    r"\s*\(v?\d+(?:\.\d+)*\)$", r"\s*（v?\d+(?:\.\d+)*）$",
    r"[\s_\-]+v\d+(?:\.\d+)*$", r"[\s_\-]+副本$", r"\s*副本$",
    r"[\s_\-]+copy(?:\s*\d*)$", r"[\s_\-]+final(?:\s*\d*)$",
    r"[\s_\-]+draft(?:\s*\d*)$", r"[\s_\-]+new$", r"[\s_\-]+old$",
]
VERSION_RE = re.compile(r"[vV](\d+(?:\.\d+)*)")


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_stem(name):
    stem = os.path.splitext(name)[0].strip().lower()
    changed = True
    while changed:
        changed = False
        for pat in COPY_PATTERNS:
            new = re.sub(pat, "", stem, flags=re.IGNORECASE)
            if new != stem:
                stem, changed = new.strip(), True
    return stem


def read_text(path, limit=None):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit) if limit else fh.read()
    except OSError:
        return None


def guess_title(name, text):
    if text:
        for line in text.splitlines():
            s = line.strip().lstrip("#").strip()
            if s:
                return s[:120]
    return os.path.splitext(name)[0]


# --------------------------------------------------------------- catalog

def load_sidecars(paths):
    """Load metadata sidecars (.json or .csv). Returns {filename_key: dict}."""
    out = {}
    for p in paths or []:
        if p.lower().endswith(".json"):
            try:
                data = json.loads(read_text(p) or "")
            except ValueError:
                continue
            rows = data if isinstance(data, list) else [data]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = (row.get("file") or row.get("filename")
                       or row.get("path") or row.get("name"))
                if key:
                    out[os.path.basename(str(key))] = row
        elif p.lower().endswith(".csv"):
            text = read_text(p)
            if text is None:
                continue
            for row in csv.DictReader(text.splitlines()):
                key = (row.get("file") or row.get("filename")
                       or row.get("path") or row.get("name"))
                if key:
                    out[os.path.basename(str(key))] = dict(row)
    return out


def cmd_catalog(args):
    root = os.path.abspath(args.root)
    sidecars = load_sidecars(args.meta)
    notes_text = "\n".join(read_text(p) or "" for p in (args.notes or []))

    records = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            ext = os.path.splitext(fn)[1].lower()
            rec = {"path": rel, "name": fn, "ext": ext,
                   "id": None, "sha256": None, "size": None,
                   "mtime": None, "readable": os.access(full, os.R_OK)}
            try:
                st = os.stat(full)
                rec["size"] = st.st_size
                rec["mtime"] = datetime.datetime.fromtimestamp(
                    st.st_mtime, datetime.timezone.utc).isoformat()
                if rec["readable"]:
                    rec["sha256"] = sha256_file(full)
                    rec["content_id"] = rec["sha256"][:12]
                    # record id is unique per FILE (path-based); content_id
                    # collapses identical content across filenames
                    rec["id"] = hashlib.sha256(
                        rel.encode("utf-8")).hexdigest()[:12]
            except OSError as exc:
                rec["error"] = str(exc)
            text = None
            if ext in TEXT_EXTS and rec["readable"]:
                text = read_text(full, EXCERPT_CHARS)
            rec["title"] = guess_title(fn, text)
            if text:
                rec["excerpt"] = text
            meta = sidecars.get(fn)
            if meta:
                rec["metadata"] = meta
                rec["metadata_source"] = "sidecar"
            records.append(rec)

    by_id = {r["id"]: r for r in records if r.get("id")}
    edges = []

    # duplicate edges: identical content hash
    by_hash = {}
    for r in records:
        if r.get("sha256"):
            by_hash.setdefault(r["sha256"], []).append(r)
    for h, group in by_hash.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda r: (len(r["name"]), r["path"]))
        canon = group[0]
        canon.setdefault("role", "canonical")
        for dup in group[1:]:
            dup["duplicate_of"] = canon["id"]
            edges.append({"src": dup["id"], "dst": canon["id"],
                          "kind": "duplicate_of",
                          "evidence": "identical sha256 " + h[:16]})

    # alias / version edges: same normalised stem and extension
    clusters = {}
    for r in records:
        if r.get("id"):
            clusters.setdefault((norm_stem(r["name"]), r["ext"]),
                                []).append(r)
    for (stem, ext), group in sorted(clusters.items()):
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda r: r["path"])
        if all("duplicate_of" in g or g is group[0] for g in group[1:]) \
                and len({g["sha256"] for g in group}) == 1:
            continue  # pure duplicate group, already recorded
        for g in group:
            g.setdefault("version_cluster", stem)
        ordered = sorted(
            group,
            key=lambda r: ((VERSION_RE.search(
                os.path.splitext(r["name"])[0]) is None),
                [int(x) for x in (VERSION_RE.search(
                    os.path.splitext(r["name"])[0]).group(1).split(".")
                    if VERSION_RE.search(os.path.splitext(r["name"])[0])
                    else [0])],
                r["mtime"] or "9999", r["path"]))
        for older, newer in zip(ordered, ordered[1:]):
            if older["sha256"] == newer["sha256"]:
                continue
            edges.append({"src": older["id"], "dst": newer["id"],
                          "kind": "superseded_by",
                          "evidence": "same stem '%s'; version marker / "
                                      "mtime order" % stem})

    # administrative note edges (explicit statements win over heuristics)
    def find_record(fragment):
        frag = fragment.strip("《》\"'`，。；;,. ")
        if not frag:
            return None
        for r in records:
            # filename inside the captured fragment, or vice versa
            if r["name"] in frag or (len(frag) >= 4 and frag in r["name"]):
                return r
        return None

    for line in notes_text.splitlines():
        m = re.search(r"(.+?)\s*(?:替代|取代|supersedes?|replaces?)\s*(\S+)",
                      line.strip(), re.I)
        if not m:
            continue
        newer = find_record(m.group(1))
        older = find_record(m.group(2))
        if newer and older and newer["id"] != older["id"]:
            edges.append({"src": older["id"], "dst": newer["id"],
                          "kind": "superseded_by",
                          "evidence": "administrative note: " + line.strip()[:200]})

    # de-duplicate edges; an administrative-note statement is stronger
    # evidence than a heuristic, so it wins for the same (src,dst,kind)
    edges.sort(key=lambda e: 0 if e["evidence"].startswith(
        "administrative note") else 1)
    seen, uniq = set(), []
    for e in edges:
        key = (e["src"], e["dst"], e["kind"])
        if key not in seen:
            seen.add(key)
            uniq.append(e)

    n = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in records:
            r["edges"] = [e for e in uniq
                          if e["src"] == r.get("id")
                          or e["dst"] == r.get("id")]
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    edges_path = os.path.splitext(args.out)[0] + ".edges.json"
    with open(edges_path, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": utcnow(), "edges": uniq}, fh,
                  ensure_ascii=False, indent=2)
    print("catalog: %d records, %d edges -> %s (+ %s)"
          % (n, len(uniq), args.out, edges_path))
    return 0


# ---------------------------------------------------------------- index

SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
  id TEXT PRIMARY KEY, path TEXT, name TEXT, ext TEXT, title TEXT,
  sha256 TEXT, size INTEGER, mtime TEXT, role TEXT,
  duplicate_of TEXT, version_cluster TEXT, excerpt TEXT, metadata TEXT);
CREATE TABLE IF NOT EXISTS edges(
  src TEXT, dst TEXT, kind TEXT, evidence TEXT);
"""


def connect(db):
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    return con


def fts_available(con):
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING "
                    "fts5(title, name, excerpt, metadata, path)")
        return True
    except sqlite3.OperationalError:
        return False


def cmd_index(args):
    con = connect(args.db)
    use_fts = fts_available(con)
    seen_edges = set()
    n = e_n = 0
    with open(args.catalog, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if not r.get("id"):
                continue
            con.execute(
                "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["id"], r["path"], r["name"], r["ext"], r.get("title"),
                 r.get("sha256"), r.get("size"), r.get("mtime"),
                 r.get("role"), r.get("duplicate_of"),
                 r.get("version_cluster"), r.get("excerpt"),
                 json.dumps(r.get("metadata", {}), ensure_ascii=False)))
            if use_fts:
                con.execute("DELETE FROM fts WHERE rowid IN "
                            "(SELECT rowid FROM fts WHERE path=?)",
                            (r["path"],))
                con.execute("INSERT INTO fts(title,name,excerpt,metadata,path)"
                            " VALUES(?,?,?,?,?)",
                            (r.get("title") or "", r["name"],
                             r.get("excerpt") or "",
                             json.dumps(r.get("metadata", {}),
                                        ensure_ascii=False),
                             r["path"]))
            for e in r.get("edges", []):
                key = (e["src"], e["dst"], e["kind"])
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                con.execute("INSERT INTO edges VALUES(?,?,?,?)",
                            (e["src"], e["dst"], e["kind"],
                             e.get("evidence", "")))
                e_n += 1
            n += 1
    con.commit()
    print("index: %d records, %d edge rows, fts5=%s -> %s"
          % (n, e_n, use_fts, args.db))
    return 0


# ---------------------------------------------------------------- query

CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")


def tokenize(q):
    return [t for t in re.split(r"\s+", q.strip()) if t]


def expand_terms(terms):
    """Add CJK bigrams for long unsegmented terms (Chinese/Japanese
    questions arrive without whitespace, so a whole sentence is one
    'term'; bigrams recover recall without inventing semantics)."""
    out = []
    for t in terms:
        out.append(t)
        core = t.strip("？?。，、；：,.;:!?（）()《》\"'")
        if len(core) > 2 and CJK_RE.search(core):
            out.extend(core[i:i + 2] for i in range(len(core) - 1))
    seen, res = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            res.append(t)
    return res


def snippet(text, terms, width=90):
    if not text:
        return ""
    low = text.lower()
    pos = -1
    for t in terms:
        pos = low.find(t.lower())
        if pos >= 0:
            break
    if pos < 0:
        return text[:width]
    start = max(0, pos - width // 3)
    return text[start:start + width].replace("\n", " ")


def run_query(con, q, k):
    terms = tokenize(q)
    hits = {}
    has_fts = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fts'"
    ).fetchone() is not None
    if has_fts and terms:
        # AND of quoted tokens (precision first); on syntax error or
        # zero rows, fall through to the scored substring pass.
        match = " AND ".join('"%s"' % t.replace('"', ' ') for t in terms)
        try:
            rows = con.execute(
                "SELECT path, title, name, excerpt, metadata FROM fts "
                "WHERE fts MATCH ? ORDER BY rank LIMIT ?",
                (match, k * 4)).fetchall()
            for path, title, name, excerpt, meta in rows:
                hits[path] = {"path": path, "matched": "fts",
                              "snippet": snippet(excerpt or title, terms),
                              "score": len(terms) + 1}
        except sqlite3.OperationalError:
            pass
    if not hits:
        # scored substring pass over every field, OR semantics; long CJK
        # terms are expanded into bigrams so unsegmented questions match.
        subs = expand_terms(terms)
        full_terms = set(t.lower() for t in terms)
        rows = con.execute(
            "SELECT id,path,name,title,excerpt,metadata FROM files").fetchall()
        for rid, path, name, title, excerpt, meta in rows:
            best = None
            for field, text in (("title", title or ""), ("name", name),
                                ("excerpt", excerpt or ""),
                                ("metadata", meta or ""), ("path", path)):
                tl = [t for t in subs if t and t.lower() in text.lower()]
                if tl and (best is None or len(tl) > len(best[2])):
                    best = (field, text, tl)
            if not best or path in hits:
                continue
            # Relevance gate: a full original term always counts; bare
            # bigram overlap needs >=3 matched bigrams, otherwise one
            # shared character pair (e.g. "催化") would fabricate recall.
            full_hit = any(t.lower() in full_terms for t in best[2])
            if not full_hit and len(best[2]) < 3:
                continue
            hits[path] = {"path": path, "matched": best[0],
                          "snippet": snippet(best[1], best[2]),
                          "score": len(best[2]) + (len(subs) if full_hit else 0),
                          "terms": best[2]}
    ranked = sorted(hits.values(),
                    key=lambda h: (-h.get("score", 0), h["path"]))[:k]
    out = []
    for h in ranked:
        row = con.execute(
            "SELECT id,title,sha256,mtime,role,duplicate_of,"
            "version_cluster FROM files WHERE path=?",
            (h["path"],)).fetchone()
        if not row:
            continue
        edges = con.execute(
            "SELECT src,dst,kind,evidence FROM edges WHERE src=? OR dst=?",
            (row[0], row[0])).fetchall()
        out.append({
            "id": row[0], "path": h["path"], "title": row[1],
            "sha256": row[2], "mtime": row[3], "role": row[4],
            "duplicate_of": row[5], "version_cluster": row[6],
            "matched_field": h["matched"], "snippet": h["snippet"],
            "edges": [{"src": s, "dst": d, "kind": knd, "evidence": ev}
                      for s, d, knd, ev in edges],
        })
    return out


def cmd_query(args):
    con = connect(args.db)
    hits = run_query(con, args.q, args.k)
    result = {"query": args.q, "k": args.k, "hit_count": len(hits),
              "hits": hits}
    if not hits:
        terms = tokenize(args.q)
        result["recall_note"] = (
            "0 hits. Suggested broadening: search individual terms %s; "
            "check whether the topic lives in administrative notes or "
            "metadata fields not indexed; consider synonym or language "
            "variants (zh/en)." % terms)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    print(payload)
    return 0


# --------------------------------------------------------------- answer

def cmd_answer(args):
    con = connect(args.db)
    questions = []
    if args.questions.endswith(".json"):
        data = json.loads(read_text(args.questions) or "[]")
        questions = data if isinstance(data, list) else [data]
    else:
        for line in (read_text(args.questions) or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                questions.append(json.loads(line))
            except ValueError:
                questions.append({"question": line})
    rows = []
    for i, q in enumerate(questions, 1):
        qtext = q.get("question") if isinstance(q, dict) else str(q)
        hits = run_query(con, qtext, args.k)
        if hits:
            rows.append({
                "qid": q.get("id", "q%d" % i) if isinstance(q, dict)
                       else "q%d" % i,
                "question": qtext, "status": "answered",
                "evidence": [{"id": h["id"], "path": h["path"],
                              "title": h["title"], "sha256": h["sha256"],
                              "matched_field": h["matched_field"],
                              "snippet": h["snippet"]} for h in hits],
                "note": "evidence-ranked hits; cite id/path when reusing"})
        else:
            rows.append({
                "qid": q.get("id", "q%d" % i) if isinstance(q, dict)
                       else "q%d" % i,
                "question": qtext, "status": "unanswered",
                "evidence": [],
                "reason": "no catalog record matched; abstained rather "
                          "than fabricate"})
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_ok = sum(1 for r in rows if r["status"] == "answered")
    print("answer: %d/%d questions answered -> %s"
          % (n_ok, len(rows), args.out))
    return 0


# ------------------------------------------------------------- contract

def cmd_contract(args):
    case = json.loads(read_text(args.case) or "{}")
    contract = (case.get("output_contract")
                or case.get("output-contract") or {})
    if isinstance(contract, dict):
        fields = list(contract.keys())
    elif isinstance(contract, list):
        fields = [f["name"] if isinstance(f, dict) else str(f)
                  for f in contract]
    else:
        fields = []
    case_id = case.get("case_id") or case.get("id") or "unknown"

    result = {}
    if args.draft and os.path.exists(args.draft):
        result = json.loads(read_text(args.draft) or "{}")
    result["case_id"] = case_id

    mapping = {}
    for group in args.map or []:
        for m in group:
            if "=" in m:
                key, path = m.split("=", 1)
                mapping[key] = path

    filled, missing = [], []
    for f in fields:
        if f == "status":
            continue  # filled from the computed run status below
        if f in result and result[f] not in (None, "", [], {}):
            filled.append(f)
            continue
        src = mapping.get(f)
        if src and os.path.exists(src):
            try:
                result[f] = json.loads(read_text(src) or "null")
                filled.append(f)
                continue
            except ValueError:
                result[f] = read_text(src)
                filled.append(f)
                continue
        result[f] = {"status": "not_produced",
                     "reason": "no artifact mapped to this contracted "
                               "field; honestly marked rather than "
                               "fabricated"}
        missing.append(f)

    result["status"] = "partial" if missing else "complete"
    result.setdefault("generated_at", utcnow())
    gaps = result.setdefault("contract_gaps", missing)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("contract: case_id=%s, %d/%d fields filled, gaps=%s -> %s"
          % (case_id, len(filled), len(fields), gaps, args.out))
    return 0 if not missing else 1


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("catalog")
    p.add_argument("--root", required=True)
    p.add_argument("--meta", nargs="*", default=[])
    p.add_argument("--notes", nargs="*", default=[])
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("index")
    p.add_argument("--catalog", required=True)
    p.add_argument("--db", required=True)
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("query")
    p.add_argument("--db", required=True)
    p.add_argument("--q", required=True)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("answer")
    p.add_argument("--db", required=True)
    p.add_argument("--questions", required=True)
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_answer)

    p = sub.add_parser("contract")
    p.add_argument("--case", required=True)
    p.add_argument("--draft", default=None)
    p.add_argument("--map", nargs="+", action="append", default=[],
                   metavar="FIELD=PATH",
                   help="may be repeated; each occurrence takes one or "
                        "more FIELD=PATH pairs")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_contract)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
