#!/usr/bin/env python3
"""Build a deterministic, stdlib-only inverted index over precipitated reading knowledge.

Inputs (each optional, but at least one is required):
  --annotations  annotations.jsonl : {annotation_id,file,page,type,category,color_hex,
                                       anchored_text,contents,tags?}
  --notes        notes.jsonl       : {note_id,note_type,claim,evidence:[{file,page,quote}],
                                       tags,created_at?}
  --inventory    files_inventory.json : {files:[{relpath,sha256,size,mtime,...}]}

Output:
  --out          index.json  (deterministic: sorted keys, no wall-clock fields)

Tokenization: lowercase [a-z0-9]+ runs for latin text; bigrams over CJK runs
(U+3400-U+4DBF, U+4E00-U+9FFF); a lone CJK char is kept as a unigram.
Indexed fields per document: text, tags, type, file. Every document keeps its full
source locator (kind, id, file, page, date). Dates come from created_at (notes) or
the inventory mtime of the owning file (annotations, file docs), normalized to
YYYY-MM-DD (UTC for epoch numbers).

The index meta block records the input paths exactly as passed plus their sha256,
so gate.py can replay the build byte-for-byte. Exit codes: 0 ok, 2 usage/input error.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

LATIN_RE = re.compile(r"[a-z0-9]+")


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def _is_cjk(ch):
    return ("\u3400" <= ch <= "\u4dbf") or ("\u4e00" <= ch <= "\u9fff")


def tokenize(text):
    """Lowercase latin words + CJK bigrams; a lone CJK char is kept as a unigram."""
    tokens = []
    latin = []
    cjk = []

    def flush_latin():
        if latin:
            tokens.extend(LATIN_RE.findall("".join(latin)))
            latin.clear()

    def flush_cjk():
        if cjk:
            if len(cjk) == 1:
                tokens.append(cjk[0])
            else:
                for i in range(len(cjk) - 1):
                    tokens.append("".join(cjk[i:i + 2]))
            cjk.clear()

    for ch in (text or "").lower():
        if _is_cjk(ch):
            flush_latin()
            cjk.append(ch)
        else:
            flush_cjk()
            latin.append(ch)
    flush_latin()
    flush_cjk()
    return tokens


def norm_date(value):
    """Normalize created_at / mtime to YYYY-MM-DD (epoch numbers treated as UTC)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d")
    s = str(value).strip()
    return s[:10] if len(s) >= 10 else (s or None)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                die(f"{path}:{lineno}: invalid JSON: {exc}")
    return rows


def dump_index(index):
    """Canonical deterministic serialization (sorted keys, UTF-8, trailing newline)."""
    return json.dumps(index, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def build(annotations_path=None, notes_path=None, inventory_path=None):
    docs = {}
    mtime_by_file = {}
    counts = {"annotations": 0, "notes": 0, "files": 0}

    if inventory_path:
        with open(inventory_path, encoding="utf-8") as fh:
            inv = json.load(fh)
        for entry in inv.get("files", []):
            rel = entry.get("relpath")
            if not rel:
                continue
            date = norm_date(entry.get("mtime"))
            mtime_by_file[rel] = date
            doc_id = "file:" + rel
            docs[doc_id] = {
                "kind": "file", "id": doc_id, "file": rel, "files": [rel],
                "page": None, "type": "file", "tags": [], "date": date,
                "text": rel,
            }
            counts["files"] += 1

    if annotations_path:
        for a in read_jsonl(annotations_path):
            aid = a.get("annotation_id") or "ann-%04d" % (counts["annotations"] + 1)
            f = a.get("file")
            text = "\n".join(x for x in [a.get("anchored_text"), a.get("contents")] if x)
            docs[aid] = {
                "kind": "annotation", "id": aid, "file": f,
                "files": [f] if f else [],
                "page": a.get("page"), "type": a.get("type") or "annotation",
                "tags": sorted(a.get("tags") or []),
                "date": mtime_by_file.get(f),
                "text": text,
            }
            counts["annotations"] += 1

    if notes_path:
        for n in read_jsonl(notes_path):
            nid = n.get("note_id") or "note-%04d" % (counts["notes"] + 1)
            evidence = n.get("evidence") or []
            quotes = [e.get("quote", "") for e in evidence if isinstance(e, dict)]
            files = sorted({e.get("file") for e in evidence
                            if isinstance(e, dict) and e.get("file")})
            first = next((e for e in evidence if isinstance(e, dict)), {})
            text = "\n".join(x for x in [n.get("claim")] + quotes if x)
            docs[nid] = {
                "kind": "note", "id": nid,
                "file": files[0] if files else None, "files": files,
                "page": first.get("page"),
                "type": n.get("note_type") or "note",
                "tags": sorted(n.get("tags") or []),
                "date": norm_date(n.get("created_at")) or
                        (mtime_by_file.get(files[0]) if files else None),
                "text": text,
            }
            counts["notes"] += 1

    inverted = {}
    for doc_id in sorted(docs):
        d = docs[doc_id]
        for field in ("text", "tags", "type", "file"):
            value = d.get(field)
            if field == "tags":
                value = " ".join(value or [])
            if value is None:
                continue
            tf = {}
            for tok in tokenize(str(value)):
                tf[tok] = tf.get(tok, 0) + 1
            for tok in sorted(tf):
                inverted.setdefault(tok, {}).setdefault(doc_id, {})[field] = tf[tok]

    inputs = {"annotations": annotations_path, "notes": notes_path,
              "inventory": inventory_path}
    index = {
        "meta": {
            "format": "retrieval-gate-index",
            "version": 1,
            "inputs": inputs,
            "input_sha256": {k: sha256_file(p) for k, p in sorted(inputs.items()) if p},
            "counts": {**counts, "documents": len(docs), "terms": len(inverted)},
        },
        "docs": docs,
        "index": inverted,
    }
    return index


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build a deterministic inverted index over precipitated reading "
                    "knowledge (annotations + notes + file inventory).")
    ap.add_argument("--annotations", help="annotations.jsonl path")
    ap.add_argument("--notes", help="notes.jsonl path")
    ap.add_argument("--inventory", help="files_inventory.json path")
    ap.add_argument("--out", required=True, help="output index.json path")
    args = ap.parse_args(argv)

    if not (args.annotations or args.notes or args.inventory):
        die("at least one of --annotations/--notes/--inventory is required")
    for label, p in [("--annotations", args.annotations),
                     ("--notes", args.notes),
                     ("--inventory", args.inventory)]:
        if p and not os.path.isfile(p):
            die(f"{label}: file not found: {p}")

    index = build(args.annotations, args.notes, args.inventory)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(dump_index(index))
    c = index["meta"]["counts"]
    print(f"documents: annotations={c['annotations']} notes={c['notes']} "
          f"files={c['files']} total={c['documents']} terms={c['terms']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
