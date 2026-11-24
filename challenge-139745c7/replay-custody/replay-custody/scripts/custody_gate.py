#!/usr/bin/env python3
"""Evidence verification gate. No card enters the answer unless it passes.

Checks per card:
  1. the cited file still hashes to the registered sha256;
  2. `quote` is a verbatim substring of the file's extracted text;
  3. if char_start/char_end are given, the slice equals `quote`.

Failed cards are written to `rejected` with the precise reason and are never
silently rewritten. `not_found` cards pass through as honest negatives.

Usage: custody_gate.py WORK_DIR OUT_JSON
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import custody_journal  # noqa: E402


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".csv", ".tsv", ".log", ".json", ".tex"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None
    if ext == ".pdf" and shutil.which("pdftotext"):
        try:
            p = subprocess.run(["pdftotext", path, "-"], capture_output=True,
                               timeout=120)
            return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None
        except Exception:
            return None
    if ext in (".docx", ".xlsx", ".pptx"):
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                return "\n".join(re.sub(r"<[^>]+>", " ",
                                        z.read(n).decode("utf-8", "replace"))
                                 for n in z.namelist() if n.endswith(".xml"))
        except Exception:
            return None
    return None


def main():
    work, out_p = sys.argv[1], sys.argv[2]
    data = json.load(open(os.path.join(work, "evidence_cards.json"),
                          encoding="utf-8"))
    manifest = {s["file"]: s for s in json.load(
        open(os.path.join(work, "sources_manifest.json"),
             encoding="utf-8"))["sources"]}
    root = json.load(open(os.path.join(work, "sources_manifest.json"),
                          encoding="utf-8"))["library_root"]
    verified, rejected = [], []
    for card in data["cards"]:
        if card.get("status") == "not_found":
            verified.append(card)
            continue
        reasons = []
        path = os.path.join(root, card["file"])
        if not os.path.isfile(path):
            reasons.append("file_missing")
        else:
            if sha256_of(path) != card.get("sha256"):
                reasons.append("sha256_mismatch: file changed after registration")
            text = extract_text(path)
            if text is None:
                reasons.append("text_unavailable_for_verification")
            else:
                quote = card.get("quote", "")
                if quote not in text:
                    reasons.append("quote_not_verbatim: 引文不是原文逐字子串")
                cs, ce = card.get("char_start"), card.get("char_end")
                if cs is not None and ce is not None and text[cs:ce] != quote:
                    reasons.append("char_interval_mismatch")
        if reasons:
            rejected.append({"card": card, "reasons": reasons})
        else:
            verified.append(card)
    out = {"verified": verified, "rejected": rejected,
           "n_verified": len(verified), "n_rejected": len(rejected)}
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    custody_journal.append(work, "gate",
                           "verified=%d rejected=%d" % (len(verified),
                                                        len(rejected)), out_p)
    print(json.dumps({"n_verified": len(verified),
                      "n_rejected": len(rejected)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
