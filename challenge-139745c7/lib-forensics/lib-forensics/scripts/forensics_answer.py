#!/usr/bin/env python3
"""Answer case questions using ONLY audit-verified files.

Extracts text from verified files (text formats directly; PDF via pdftotext
when present), runs keyword overlap scoring per question, and attaches
integrity evidence (sha256 prefix + audit status) to every cited file.

Usage: forensics_answer.py CASE_PROFILE INVENTORY OUT_JSON
"""
import json
import os
import re
import shutil
import subprocess
import sys

STOP = set("的了和是在有与及或其对这那中上个一为以于哪些哪个什么哪份"
           "the a an of in on for to is are was were and or which what")
CJK = re.compile(r"[一-鿿]")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{1,}|[一-鿿]{2,}")


def tokens(text):
    out = []
    for t in TOKEN.findall(text):
        t = t.lower()
        if t not in STOP and len(t) > 1:
            out.append(t)
    return out


def extract_text(path, true_type):
    if true_type in ("utf8-text", "json-text?"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""
    if true_type == "pdf" and shutil.which("pdftotext"):
        try:
            p = subprocess.run(["pdftotext", path, "-"], capture_output=True, timeout=120)
            if p.returncode == 0:
                return p.stdout.decode("utf-8", "replace")
        except Exception:
            return ""
    if true_type in ("docx", "xlsx", "pptx"):
        try:
            import zipfile
            with zipfile.ZipFile(path) as z:
                parts = []
                for n in z.namelist():
                    if n.endswith(".xml") and ("document" in n or "sheet" in n or "slide" in n):
                        xml = z.read(n).decode("utf-8", "replace")
                        parts.append(re.sub(r"<[^>]+>", " ", xml))
                return "\n".join(parts)
        except Exception:
            return ""
    return ""


def main():
    profile_p, inv_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    profile = json.load(open(profile_p, encoding="utf-8"))
    inv = json.load(open(inv_p, encoding="utf-8"))
    lib = inv["library_root"]
    usable = [r for r in inv["files"]
              if r["status"] in ("verified",) and r.get("canonical", True)]
    excluded = [r for r in inv["files"] if r not in usable]

    corpus = []
    for r in usable:
        text = extract_text(os.path.join(lib, r["path"]), r.get("true_type", ""))
        corpus.append({"path": r["path"], "sha16": (r.get("sha256") or "")[:16],
                       "true_type": r.get("true_type"), "text": text,
                       "tokens": set(tokens(r["path"] + " " + text))})

    answers = []
    for q in profile.get("questions", []):
        qtext = q.get("text") if isinstance(q, dict) else str(q)
        qt = set(tokens(qtext or ""))
        scored = []
        for c in corpus:
            hit = qt & c["tokens"]
            if hit:
                scored.append((len(hit), c, sorted(hit)))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            answers.append({"question": qtext, "status": "no_match",
                            "evidence": [],
                            "note": "在通过审计的 %d 份文件中无任何词项命中；"
                                    "被排除文件 %d 份未参与作答" % (len(corpus), len(excluded))})
            continue
        top = scored[0][0]
        best = [s for s in scored if s[0] == top][:5]
        answers.append({
            "question": qtext,
            "status": "answered",
            "evidence": [{"file": c["path"], "sha256_16": c["sha16"],
                          "audit_status": "verified", "matched_terms": terms}
                         for _s, c, terms in best],
            "note": "仅引用通过法医审计的文件；副本与可疑件见 inventory.json"})
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump({"answers": answers,
                   "excluded_files": [{"path": r["path"], "status": r["status"],
                                       "issues": r["issues"]} for r in excluded]},
                  f, ensure_ascii=False, indent=2)
    print(json.dumps({"n_answers": len(answers),
                      "n_excluded": len(excluded)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
