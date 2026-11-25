#!/usr/bin/env python3
"""extract_source.py — 从 /input 取实际源文（PDF→pdftotext，文本→复制），写 source.md 与 provenance。"""
import argparse, hashlib, json, os, shutil, subprocess, sys

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    prov = {"files": [], "source_file": None, "extraction": "text-copy", "unreadable": []}
    src = None
    for name in sorted(os.listdir(a.input)):
        p = os.path.join(a.input, name)
        if not os.path.isfile(p):
            continue
        prov["files"].append({"name": name, "sha256": sha256(p)})
        if src is None and name.lower().endswith((".txt", ".md", ".pdf")):
            src = p
    if src is None:
        print("ERROR: no source under /input", file=sys.stderr)
        sys.exit(2)
    prov["source_file"] = os.path.basename(src)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    if src.lower().endswith(".pdf"):
        prov["extraction"] = "pdftotext"
        try:
            r = subprocess.run(["pdftotext", "-enc", "UTF-8", src, a.out],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                prov["unreadable"].append("pdftotext failed")
                sys.exit(3)
        except FileNotFoundError:
            prov["unreadable"].append("pdftotext unavailable")
            sys.exit(3)
    else:
        shutil.copyfile(src, a.out)
    text = open(a.out, encoding="utf-8", errors="replace").read()
    if len(text.strip()) < 20:
        prov["unreadable"].append("text layer almost empty")
    json.dump(prov, open(os.path.join(os.path.dirname(a.out), "provenance.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"source.md: {len(text)} chars from {prov['source_file']} ({prov['extraction']})")

if __name__ == "__main__":
    main()
