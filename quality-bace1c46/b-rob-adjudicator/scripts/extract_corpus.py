#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_corpus.py -- defensive input parsing and full-text extraction.

- Parses /input/case.json (case_id, document list, output_contract).
- Falls back to scanning the input dir (*.pdf -> *.txt -> *.md -> *.json
  snapshots with title/abstract).
- Extracts PDFs via `pdftotext -layout` with a pypdf fallback, then marks
  the document as failed.
- Writes pages/<doc_id>.jsonl, anchors/<doc_id>.json, docs.jsonl.
- Writes a partial /app/output/result.json (status=in_progress) within the
  first seconds, before any heavy work, so a deliverable always exists.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common_utils as cu

SCRIPT_VERSION = "extract_corpus/1.0"


# ---------------------------------------------------------------------------
# Partial result.json (written early, updated on exit)
# ---------------------------------------------------------------------------

class PartialResult:
    def __init__(self, output_dir, case_id, output_contract, task_summary):
        self.path = os.path.join(output_dir, "result.json")
        self.data = {
            "case_id": case_id,
            "output_contract": output_contract,
            "status": "in_progress",
            "task_summary": task_summary,
            "skill": "rob-signal-dual-adjudicator",
            "pipeline_stage": "extract",
            "documents": [],
            "uncertainties": [],
            "change_log": [],
            "started_epoch": time.time(),
        }

    def log(self, msg):
        self.data["change_log"].append(
            {"stage": "extract", "message": msg,
             "epoch": round(time.time(), 3)})

    def write(self):
        self.data["documents"] = self.data.get("documents", [])
        cu.write_json(self.path, self.data)


# ---------------------------------------------------------------------------
# Document discovery
# ---------------------------------------------------------------------------

def resolve_entries(entries, input_dir):
    """Turn raw case.json entries into a list of {path} or {snapshot} dicts."""
    docs, notes = [], []
    for i, ent in enumerate(entries):
        if isinstance(ent, str):
            p = ent if os.path.isabs(ent) else os.path.join(input_dir, ent)
            docs.append({"path": p, "origin": "case_list"})
        elif isinstance(ent, dict):
            p = None
            for k in ("path", "file", "pdf", "filename", "filepath", "url_path"):
                v = ent.get(k)
                if isinstance(v, str) and v.strip():
                    p = v
                    break
            if p:
                p2 = p if os.path.isabs(p) else os.path.join(input_dir, p)
                if os.path.exists(p2):
                    docs.append({"path": p2, "origin": "case_list",
                                 "meta": {k: ent.get(k) for k in
                                          ("title", "doi", "DOI", "year",
                                           "journal") if ent.get(k)}})
                    continue
            if cu.looks_like_metadata_snapshot(ent):
                docs.append({"snapshot": ent, "origin": "inline_metadata"})
            else:
                notes.append("entry %d unrecognized (no path, no metadata)" % i)
        else:
            notes.append("entry %d has unsupported type %s" % (i, type(ent)))
    return docs, notes


def scan_input_dir(input_dir):
    """Fallback collection: *.pdf -> *.txt -> *.md -> *.json snapshots."""
    docs, notes = [], []
    try:
        names = sorted(os.listdir(input_dir))
    except Exception as e:
        return [], ["cannot list input dir %s: %s" % (input_dir, e)]
    files = [os.path.join(input_dir, n) for n in names
             if os.path.isfile(os.path.join(input_dir, n))]
    pdfs = [f for f in files if f.lower().endswith(".pdf")]
    txts = [f for f in files if f.lower().endswith(".txt")]
    mds = [f for f in files if f.lower().endswith(".md")
           and os.path.basename(f).lower() != "task.md"]
    jsons = [f for f in files if f.lower().endswith(".json")
             and os.path.basename(f).lower() != "case.json"]
    for f in pdfs + txts + mds:
        docs.append({"path": f, "origin": "dir_scan"})
    for f in jsons:
        obj = cu.read_json(f, default=None)
        if cu.looks_like_metadata_snapshot(obj):
            docs.append({"path": f, "origin": "dir_scan",
                         "snapshot_file": True})
        elif isinstance(obj, list) and obj and \
                cu.looks_like_metadata_snapshot(obj[0]):
            for rec in obj:
                docs.append({"snapshot": rec, "origin": "dir_scan_list"})
        else:
            notes.append("json file %s not a metadata snapshot; skipped" % f)
    if not docs:
        notes.append("no documents found by directory scan of %s" % input_dir)
    return docs, notes


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_pdf_pages(path):
    """Return (pages[list of str], method) or (None, reason)."""
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", path, "-"],
            capture_output=True, timeout=120)
        if proc.returncode == 0:
            text = proc.stdout.decode("utf-8", "replace")
            if text.strip():
                return text.split("\f"), "pdftotext-layout"
    except FileNotFoundError:
        pass
    except Exception:
        pass
    # fallback: pypdf if importable
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(path)
        pages = []
        for pg in reader.pages:
            pages.append(pg.extract_text() or "")
        if any(p.strip() for p in pages):
            return pages, "pypdf-fallback"
        return None, "pypdf produced empty text"
    except ImportError:
        return None, "pdftotext unavailable and pypdf not importable"
    except Exception as e:
        return None, "pypdf fallback failed: %s" % e


def extract_text_pages(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    # treat form feeds as page breaks if present, else single page
    pages = text.split("\f") if "\f" in text else [text]
    return pages, "plain-text"


def snapshot_to_pages(snap):
    title = cu.extract_title(snap)
    abstract = cu.extract_abstract(snap)
    ids = []
    for k in ("DOI", "doi", "pmid", "pmcid", "journal", "year"):
        if snap.get(k):
            ids.append("%s: %s" % (k, snap.get(k)))
    text = (("Title: " + title + "\n\n") if title else "") \
        + (("Identifiers -- " + "; ".join(ids) + "\n\n") if ids else "") \
        + (("Abstract: " + abstract) if abstract else "")
    return [text], "metadata-snapshot"


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

def build_anchors(pages):
    """p<page>.¶<para> -> first 80 chars of the paragraph."""
    anchors = {}
    for pno, ptext in enumerate(pages, start=1):
        paras = [p.strip() for p in re.split(r"\n\s*\n", ptext or "")
                 if p.strip()]
        for j, para in enumerate(paras, start=1):
            key = "p%d.\u00b6%d" % (pno, j)
            anchors[key] = para[:80]
    return anchors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Extract corpus from /input")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()

    os.makedirs(args.workdir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    parsed = cu.parse_case(args.case)
    task_summary = ""
    try:
        with open(args.task, "r", encoding="utf-8", errors="replace") as f:
            task_summary = f.read()[:2000]
    except Exception:
        parsed["uncertainties"].append("task.md not readable at %s" % args.task)

    pr = PartialResult(args.output_dir, parsed["case_id"],
                       parsed["output_contract"], task_summary.strip())
    pr.data["uncertainties"].extend(parsed["uncertainties"])
    # Write the partial result.json within the first seconds, before any
    # heavy extraction work.
    pr.write()
    pr.log("partial result.json written before extraction")

    # --- discover documents ---
    if parsed["doc_entries"]:
        docs, notes = resolve_entries(parsed["doc_entries"], args.input_dir)
        pr.log("document list found under key '%s' (%d entries)"
               % (parsed.get("doc_list_key"), len(docs)))
    else:
        docs, notes = scan_input_dir(args.input_dir)
        pr.log("no document list in case.json; scanned input dir (%d found)"
               % len(docs))
    pr.data["uncertainties"].extend(notes)

    # --- persist inline snapshots as files for uniform handling ---
    snap_dir = os.path.join(args.workdir, "snapshots")
    final_docs = []
    for i, d in enumerate(docs):
        if "snapshot" in d:
            os.makedirs(snap_dir, exist_ok=True)
            sp = os.path.join(snap_dir, "snapshot_%02d.json" % i)
            cu.write_json(sp, d["snapshot"])
            final_docs.append({"path": sp, "origin": d["origin"],
                               "is_snapshot": True})
        else:
            final_docs.append(d)

    # --- extract ---
    os.makedirs(os.path.join(args.workdir, "pages"), exist_ok=True)
    os.makedirs(os.path.join(args.workdir, "anchors"), exist_ok=True)
    docs_rows = []
    used_ids = set()
    for i, d in enumerate(final_docs):
        path = d.get("path")
        base = os.path.splitext(os.path.basename(path or "doc"))[0]
        doc_id = re.sub(r"[^A-Za-z0-9_.-]", "_", base)[:48] or ("doc%02d" % i)
        if doc_id in used_ids:
            doc_id = "%s_%d" % (doc_id, i)
        used_ids.add(doc_id)
        row = {"doc_id": doc_id, "path": path, "origin": d.get("origin"),
               "sha256": None, "word_count": 0, "pages": 0,
               "grade": "failed", "method": None, "notes": []}
        if not path or not os.path.exists(path):
            row["notes"].append("file not found: %s" % path)
            docs_rows.append(row)
            continue
        row["sha256"] = cu.sha256_file(path)
        lower = path.lower()
        pages, method, grade = None, None, "fulltext"
        if d.get("is_snapshot") or d.get("snapshot_file"):
            obj = cu.read_json(path, default=None)
            if cu.looks_like_metadata_snapshot(obj):
                pages, method = snapshot_to_pages(obj)
                grade = "abstract_only"
            else:
                row["notes"].append("snapshot json not parseable")
        elif lower.endswith(".pdf"):
            pages, method = extract_pdf_pages(path)
        elif lower.endswith((".txt", ".md")):
            try:
                pages, method = extract_text_pages(path)
            except Exception as e:
                row["notes"].append("text read failed: %s" % e)
        else:
            obj = cu.read_json(path, default=None)
            if cu.looks_like_metadata_snapshot(obj):
                pages, method = snapshot_to_pages(obj)
                grade = "abstract_only"
            else:
                row["notes"].append("unsupported file type")
        if pages:
            wc = sum(cu.word_count(p) for p in pages)
            if grade == "fulltext" and wc < 800:
                grade = "abstract_only"
                row["notes"].append(
                    "short text (%d words); treated as abstract_only" % wc)
            row.update({"word_count": wc, "pages": len(pages),
                        "grade": grade, "method": method})
            cu.write_jsonl(
                os.path.join(args.workdir, "pages", doc_id + ".jsonl"),
                [{"page": n, "text": t}
                 for n, t in enumerate(pages, start=1)])
            cu.write_json(
                os.path.join(args.workdir, "anchors", doc_id + ".json"),
                build_anchors(pages))
        else:
            row["notes"].append("extraction failed: %s" % (method or "unknown"))
            row["grade"] = "failed"
        docs_rows.append(row)

    cu.write_jsonl(os.path.join(args.workdir, "docs.jsonl"), docs_rows)
    pr.data["documents"] = [
        {k: r[k] for k in ("doc_id", "grade", "word_count", "pages",
                           "method", "notes")} for r in docs_rows]
    pr.data["pipeline_stage"] = "extract_done"
    pr.log("extraction finished: %d docs (%d fulltext, %d abstract_only, "
           "%d failed)" % (
               len(docs_rows),
               sum(1 for r in docs_rows if r["grade"] == "fulltext"),
               sum(1 for r in docs_rows if r["grade"] == "abstract_only"),
               sum(1 for r in docs_rows if r["grade"] == "failed")))
    if not docs_rows:
        pr.data["status"] = "completed_with_warnings"
        pr.data["uncertainties"].append("zero documents discovered")
    pr.write()
    print(json.dumps({"docs": len(docs_rows),
                      "result_json": pr.path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
