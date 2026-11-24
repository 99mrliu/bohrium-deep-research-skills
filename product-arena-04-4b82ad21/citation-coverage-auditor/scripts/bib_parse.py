#!/usr/bin/env python3
"""bib_parse.py - normalize references.json and cross-check its references.md rendering.

Part of the citation-coverage-auditor skill. Pure Python 3 stdlib.

Outputs (written to --out-dir):
  bib.json           normalized bibliography: list of entries in bibliography order,
                     each {key, number, authors, year, title, journal, doi,
                     abstract, evidence_level}
  xcheck_report.json machine-readable cross-check of the two representations
  xcheck_report.md   human-readable rendering of the same report

Exit codes: 0 = no disagreements, 1 = disagreements found, 2 = usage error.
Disagreements are REPORTED, never silently fixed.
"""
import argparse
import json
import re
import sys
from pathlib import Path

FIELDS = ["authors", "year", "title", "journal", "doi", "abstract"]


def norm_ws(s):
    """Collapse all whitespace runs to single spaces and strip."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def norm_cmp(s):
    """Comparison normalization: whitespace + trivial punctuation differences."""
    s = norm_ws(s)
    s = s.replace("*", "")
    s = re.sub(r"[\s.]+$", "", s)  # trailing periods / spaces
    return s


def load_json_refs(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        refs = data.get("references", [])
    elif isinstance(data, list):
        refs = data
    else:
        raise ValueError("references.json must be a list or an object with a 'references' key")
    out = []
    for i, r in enumerate(refs, start=1):
        key = r.get("key") or r.get("id") or "ref%02d" % i
        authors = [norm_ws(a) for a in (r.get("authors") or [])]
        abstract = norm_ws(r.get("abstract", ""))
        out.append({
            "key": key,
            "number": i,
            "authors": authors,
            "year": r.get("year"),
            "title": norm_ws(r.get("title", "")),
            "journal": norm_ws(r.get("journal", "")),
            "doi": norm_ws(r.get("doi", "")),
            "abstract": abstract,
            "evidence_level": "abstract" if abstract else "title-only",
        })
    return out


MD_ENTRY_RE = re.compile(r"^(\d+)\.\s+(.*)$")
MD_AUTHORS_YEAR_RE = re.compile(r"^(?P<authors>.*?)\s*\((?P<year>\d{4})\)\.?\s+(?P<rest>.*)$")
MD_DOI_RE = re.compile(r"\bdoi:\s*(\S+)", re.IGNORECASE)
MD_ITALIC_RE = re.compile(r"\*([^*]+)\*")
MD_ABSTRACT_RE = re.compile(r"^-\s*Abstract:\s*(.*)$", re.IGNORECASE)


def parse_md(path):
    """Parse the human-readable numbered rendering.

    Expected entry shape (tolerant of missing abstract / non-italic journal):
      N. Author, A., Author, B. (YYYY). Title. *Journal* doi:10.xxxx/yyy
         - Abstract: ...
    Returns a list of dicts: {md_number, authors_str, year, title, journal, doi, abstract}.
    """
    entries = []
    current = None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        m = MD_ENTRY_RE.match(line.strip())
        am = MD_ABSTRACT_RE.match(line.strip())
        if m and not line.startswith(" "):
            # Heuristic: a top-level numbered line starts a new bibliography entry
            # only if it also contains a (YYYY) group; otherwise it is list noise.
            if re.search(r"\(\d{4}\)", m.group(2)):
                if current:
                    entries.append(current)
                current = {"md_number": int(m.group(1)), "_raw": m.group(2),
                           "authors_str": "", "year": None, "title": "",
                           "journal": "", "doi": "", "abstract": ""}
                continue
        if am and current is not None:
            current["abstract"] = norm_ws(am.group(1))
            continue
        if current is not None and line.strip() and not line.lstrip().startswith("#"):
            # continuation line of the current entry
            current["_raw"] += " " + line.strip()
    if current:
        entries.append(current)

    for e in entries:
        rest = e.pop("_raw")
        dm = MD_DOI_RE.search(rest)
        if dm:
            e["doi"] = dm.group(1).rstrip(".")
            rest_wo_doi = (rest[:dm.start()] + rest[dm.end():]).strip()
        else:
            rest_wo_doi = rest
        ay = MD_AUTHORS_YEAR_RE.match(rest_wo_doi)
        if ay:
            e["authors_str"] = norm_ws(ay.group("authors"))
            e["year"] = int(ay.group("year"))
            body = ay.group("rest").strip()
        else:
            body = rest_wo_doi
        im = MD_ITALIC_RE.search(body)
        if im:
            e["journal"] = norm_ws(im.group(1)).rstrip(".")
            title = (body[:im.start()] + body[im.end():]).strip()
            e["title"] = re.sub(r"[\s.]+$", "", title)
        else:
            # No italics: assume "Title. Journal" split at the last period-space.
            parts = body.rsplit(". ", 1)
            if len(parts) == 2:
                e["title"], e["journal"] = norm_ws(parts[0]), norm_ws(parts[1]).rstrip(".")
            else:
                e["title"] = norm_ws(body).rstrip(".")
    return entries


def compare(json_refs, md_entries):
    """Cross-check the two representations. Returns (report_dict, n_disagreements)."""
    # Match md entries to json entries: prefer DOI, then normalized title, then position.
    used_json = set()
    pairs = []   # (json_entry or None, md_entry or None, how)
    for md in md_entries:
        hit = None
        how = None
        for j in json_refs:
            if j["key"] in used_json:
                continue
            if md["doi"] and j["doi"] and norm_cmp(md["doi"]).lower() == norm_cmp(j["doi"]).lower():
                hit, how = j, "doi"
                break
        if hit is None:
            for j in json_refs:
                if j["key"] in used_json:
                    continue
                if md["title"] and norm_cmp(md["title"]).lower() == norm_cmp(j["title"]).lower():
                    hit, how = j, "title"
                    break
        if hit is None and (md["md_number"] - 1) < len(json_refs) \
                and json_refs[md["md_number"] - 1]["key"] not in used_json:
            hit, how = json_refs[md["md_number"] - 1], "position"
        if hit is not None:
            used_json.add(hit["key"])
        pairs.append((hit, md, how))

    extras_md = [md for (j, md, how) in pairs if j is None]
    missing_in_md = [j for j in json_refs if j["key"] not in used_json]

    entry_reports = []
    ordering_issues = []
    n_dis = 0
    for (j, md, how) in pairs:
        if j is None:
            n_dis += 1
            continue
        fields = {}
        if md["md_number"] != j["number"]:
            ordering_issues.append({
                "key": j["key"], "json_position": j["number"],
                "md_position": md["md_number"],
                "note": "same work appears at different positions in the two representations",
            })
            n_dis += 1
        for f in FIELDS:
            if f == "authors":
                jv = ", ".join(j["authors"])
                mv = md["authors_str"]
            elif f == "year":
                jv = j["year"]
                mv = md["year"]
            else:
                jv = j.get(f, "")
                mv = md.get(f, "")
            j_empty = (jv is None or norm_ws(jv) == "")
            m_empty = (mv is None or norm_ws(mv) == "")
            if m_empty and not j_empty:
                fields[f] = {"status": "missing_in_md", "json_value": jv, "md_value": mv}
                n_dis += 1
            elif j_empty and not m_empty:
                fields[f] = {"status": "extra_in_md", "json_value": jv, "md_value": mv}
                n_dis += 1
            elif j_empty and m_empty:
                fields[f] = {"status": "absent_in_both", "json_value": jv, "md_value": mv}
            else:
                if f == "year":
                    same = (jv == mv)
                else:
                    same = norm_cmp(jv).lower() == norm_cmp(mv).lower()
                fields[f] = {"status": "ok" if same else "mismatch",
                             "json_value": jv, "md_value": mv}
                if not same:
                    n_dis += 1
        entry_reports.append({
            "key": j["key"], "matched_via": how,
            "json_position": j["number"], "md_position": md["md_number"],
            "fields": fields,
        })
    n_dis += len(extras_md) + len(missing_in_md)

    report = {
        "summary": {
            "json_entries": len(json_refs),
            "md_entries": len(md_entries),
            "matched": len(entry_reports),
            "disagreements": n_dis,
            "status": "pass" if n_dis == 0 else "disagreements_found",
        },
        "entries": entry_reports,
        "ordering_differences": ordering_issues,
        "extra_md_entries": [{"md_number": m["md_number"], "title": m["title"]} for m in extras_md],
        "json_entries_missing_in_md": [{"key": j["key"], "title": j["title"]} for j in missing_in_md],
        "policy": "Disagreements are reported, never silently fixed. Trivial "
                  "punctuation/whitespace differences are tolerated.",
    }
    return report, n_dis


def render_md_report(report):
    s = report["summary"]
    lines = [
        "# Bibliography cross-check report",
        "",
        "JSON entries: %d | MD entries: %d | matched: %d | disagreements: **%d** | status: **%s**"
        % (s["json_entries"], s["md_entries"], s["matched"], s["disagreements"], s["status"]),
        "",
        "Policy: disagreements are reported, never silently fixed; trivial",
        "punctuation/whitespace differences are tolerated.",
        "",
    ]
    if s["disagreements"] == 0:
        lines.append("All fields agree across the two provided representations.")
        lines.append("")
        return "\n".join(lines)
    lines.append("| key | field | status | json value | md value |")
    lines.append("|---|---|---|---|---|")
    for e in report["entries"]:
        for f, fr in e["fields"].items():
            if fr["status"] in ("ok", "absent_in_both"):
                continue
            lines.append("| %s | %s | %s | %s | %s |" % (
                e["key"], f, fr["status"],
                str(fr["json_value"])[:80], str(fr["md_value"])[:80]))
    for o in report["ordering_differences"]:
        lines.append("| %s | ordering | ordering_difference | position %s | position %s |"
                     % (o["key"], o["json_position"], o["md_position"]))
    for x in report["extra_md_entries"]:
        lines.append("| (none) | entry | extra_md_entry | - | md #%s: %s |"
                     % (x["md_number"], x["title"][:60]))
    for x in report["json_entries_missing_in_md"]:
        lines.append("| %s | entry | missing_in_md | %s | - |"
                     % (x["key"], x["title"][:60]))
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Normalize references.json into bib.json and cross-check the references.md rendering.")
    ap.add_argument("--json", default=None,
                    help="path to references.json (structured bibliography). May be omitted when "
                         "--md is given, in which case bib.json is built from the md alone.")
    ap.add_argument("--md", default=None,
                    help="path to references.md (human-readable rendering). If omitted, bib.json is "
                         "written from the JSON alone and no cross-check is performed.")
    ap.add_argument("--out-dir", required=True, help="directory for bib.json and xcheck reports")
    args = ap.parse_args(argv)

    if not args.json and not args.md:
        print("error: at least one of --json / --md is required", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = Path(args.md) if args.md else None
    if md_path and not md_path.is_file():
        print("error: --md file not found: %s" % md_path, file=sys.stderr)
        return 2

    if not args.json:
        # Exception path: only the readable rendering exists. Parse it and mark
        # evidence levels accordingly; no cross-check is possible.
        md_entries = parse_md(md_path)
        refs = []
        for i, m in enumerate(md_entries, start=1):
            refs.append({
                "key": "ref%02d" % i,
                "number": i,
                "authors": [a.strip() for a in
                            re.findall(r"[^,]+,\s*[^,]+?(?=,\s[^,]+,|$)",
                                       m["authors_str"])] or [m["authors_str"]],
                "year": m["year"],
                "title": m["title"],
                "journal": m["journal"],
                "doi": m["doi"],
                "abstract": m["abstract"],
                "evidence_level": "abstract" if m["abstract"] else "title-only",
            })
        (out_dir / "bib.json").write_text(
            json.dumps(refs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("note: --json missing; parsed %d entries from the md rendering only. "
              "Evidence levels marked from the md; no cross-check possible. Record the "
              "missing structured bibliography as a material gap." % len(refs),
              file=sys.stderr)
        return 0

    json_path = Path(args.json)
    if not json_path.is_file():
        print("error: --json file not found: %s" % json_path, file=sys.stderr)
        return 2
    try:
        refs = load_json_refs(json_path)
    except (ValueError, json.JSONDecodeError) as exc:
        print("error: cannot parse %s: %s" % (json_path, exc), file=sys.stderr)
        return 2

    (out_dir / "bib.json").write_text(
        json.dumps(refs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if md_path is None:
        print("note: --md not given; wrote bib.json only, no cross-check performed.", file=sys.stderr)
        return 0

    md_entries = parse_md(md_path)
    report, n_dis = compare(refs, md_entries)
    (out_dir / "xcheck_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "xcheck_report.md").write_text(render_md_report(report), encoding="utf-8")

    print("bib.json: %d entries -> %s" % (len(refs), out_dir / "bib.json"))
    print("cross-check: %d disagreement(s) -> %s" % (n_dis, out_dir / "xcheck_report.json"))
    return 1 if n_dis else 0


if __name__ == "__main__":
    sys.exit(main())
