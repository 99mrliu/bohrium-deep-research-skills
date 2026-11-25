#!/usr/bin/env python3
"""extract_source.py — 从 /input 取实际源文，写 source.md + provenance.json。

用法: extract_source.py --input /input --out /app/work/termjob/source.md
只复制/抽取，不翻译、不改写。PDF 用运行时真实存在的 pdftotext；无文字层时
记录 unreadable 而不是臆造文本。
"""
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

    prov = {"input_dir": os.path.abspath(a.input), "files": [], "source_file": None,
            "extraction": "text-copy", "unreadable": []}
    entries = sorted(os.listdir(a.input))
    src = None
    for name in entries:
        p = os.path.join(a.input, name)
        if not os.path.isfile(p):
            continue
        prov["files"].append({"name": name, "sha256": sha256(p), "bytes": os.path.getsize(p)})
        low = name.lower()
        if src is None and low.endswith((".txt", ".md")):
            src = p
        elif src is None and low.endswith(".pdf"):
            src = p
    if src is None:
        prov["unreadable"].append("no readable source file under /input")
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        open(a.out, "w", encoding="utf-8").write("")
        json.dump(prov, open(os.path.join(os.path.dirname(a.out), "provenance.json"), "w",
                             encoding="utf-8"), ensure_ascii=False, indent=2)
        print("ERROR: no source file found", file=sys.stderr)
        sys.exit(2)

    prov["source_file"] = os.path.basename(src)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    if src.lower().endswith(".pdf"):
        prov["extraction"] = "pdftotext"
        try:
            r = subprocess.run(["pdftotext", "-enc", "UTF-8", src, a.out],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0 or not os.path.exists(a.out):
                prov["unreadable"].append(f"pdftotext failed: {r.stderr.strip()[:200]}")
                sys.exit(3)
        except FileNotFoundError:
            prov["unreadable"].append("pdftotext not available in runtime")
            sys.exit(3)
    else:
        shutil.copyfile(src, a.out)

    text = open(a.out, encoding="utf-8", errors="replace").read()
    prov["text_chars"] = len(text)
    if len(text.strip()) < 20:
        prov["unreadable"].append("extracted text layer almost empty (possible scanned PDF)")
    json.dump(prov, open(os.path.join(os.path.dirname(a.out), "provenance.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"source.md written: {len(text)} chars from {prov['source_file']} "
          f"({prov['extraction']}); warnings={len(prov['unreadable'])}")

if __name__ == "__main__":
    main()
