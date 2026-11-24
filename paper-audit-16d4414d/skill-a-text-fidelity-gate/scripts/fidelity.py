#!/usr/bin/env python3
"""fidelity.py — 上游输入保真门禁（text fidelity gate）for paper-audit skills.

Pure Python 3.8+ standard library. Deterministic. Zero dependencies.
Does NOT audit the paper; it certifies that the text you are about to audit
is a faithful, complete, correctly-ordered rendering of the source, and it
anchors every sentence so later findings can be checked verbatim.

Subcommands:
  extract     --input PATH --work DIR   PDF/TXT -> work/paper.txt (+extract_meta.json)
  certificate --work DIR                paper.txt -> fidelity_certificate.json (+ .md)
  anchor      --work DIR                paper.txt -> sentences.jsonl (global ids + offsets)
  quotecheck  --work DIR --findings F   verify every finding quote is a verbatim
                                        substring of its anchored sentence

Exit codes: 0 ok / gate pass; 2 degraded (warnings, audit may proceed with
caveats); 3 fail (do not audit; mark 未检查). quotecheck: 0 pass, 4 violations.
Every failure prints an explicit reason to stderr; nothing is silent.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

CANONICAL_SECTIONS = [
    ("abstract", re.compile(r"^\s*(abstract|摘要)\s*$", re.I | re.M)),
    ("introduction", re.compile(r"^\s*(\d+\.?\s+)?(introduction|引言|绪论)\s*$", re.I | re.M)),
    ("methods", re.compile(r"^\s*(\d+\.?\s+)?(materials?\s+and\s+methods|methods?|methodology|实验方法|方法|材料与方法)\s*$", re.I | re.M)),
    ("results", re.compile(r"^\s*(\d+\.?\s+)?(results?|实验结果|结果)\s*$", re.I | re.M)),
    ("discussion", re.compile(r"^\s*(\d+\.?\s+)?(discussion|讨论)\s*$", re.I | re.M)),
    ("references", re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.I | re.M)),
]

REPLACEMENT = "�"


def eprint(*a):
    print(*a, file=sys.stderr)


def norm_text(t):
    # NFKC keeps semantics but folds full-width forms; used only for detection,
    # the anchored text itself is stored raw so quotes stay verbatim.
    return unicodedata.normalize("NFKC", t)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def atomic_write_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------- extract
def cmd_extract(args):
    os.makedirs(args.work, exist_ok=True)
    src = args.input
    if not os.path.isfile(src):
        eprint("FATAL: input not found: %s" % src)
        return 3
    meta = {"input_path": os.path.abspath(src),
            "input_sha256": sha256_file(src),
            "engine": None, "engine_returncode": None, "notes": []}
    ext = os.path.splitext(src)[1].lower()
    out_txt = os.path.join(args.work, "paper.txt")
    if ext == ".pdf":
        pdftotext = shutil.which("pdftotext")
        if pdftotext:
            p = subprocess.run([pdftotext, "-layout", src, out_txt],
                               capture_output=True, text=True)
            meta["engine"] = "pdftotext -layout"
            meta["engine_returncode"] = p.returncode
            if p.returncode != 0:
                eprint("FATAL: pdftotext failed: %s" % p.stderr.strip()[:400])
                return 3
            meta["notes"].append("layout mode preserves column/table spacing")
        else:
            eprint("FATAL: pdftotext not on PATH; use the platform pdf-text-tool "
                   "to produce paper.txt, then run with --input that .txt file")
            return 3
    else:
        with open(src, "rb") as fh:
            raw = fh.read()
        for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                text = raw.decode(enc)
                meta["engine"] = "direct-decode:%s" % enc
                break
            except UnicodeDecodeError:
                continue
        else:
            eprint("FATAL: cannot decode input as text")
            return 3
        atomic_write(out_txt, text)
    meta["output_sha256"] = sha256_file(out_txt)
    meta["output_bytes"] = os.path.getsize(out_txt)
    atomic_write_json(os.path.join(args.work, "extract_meta.json"), meta)
    print(json.dumps({"status": "ok", "engine": meta["engine"],
                      "bytes": meta["output_bytes"]}, ensure_ascii=False))
    return 0


# ------------------------------------------------------------- certificate
def detect_sections(text):
    found = {}
    for name, pat in CANONICAL_SECTIONS:
        m = pat.search(text)
        if m:
            found[name] = m.start()
    return found


def line_profile(text):
    lines = text.split("\n")
    nonempty = [ln for ln in lines if ln.strip()]
    widths = [len(ln) for ln in nonempty]
    short = sum(1 for w in widths if 0 < w < 45)
    return {
        "lines": len(lines),
        "nonempty_lines": len(nonempty),
        "median_line_chars": sorted(widths)[len(widths) // 2] if widths else 0,
        "short_line_ratio": round(short / len(widths), 4) if widths else 0.0,
    }


def cmd_certificate(args):
    paper = os.path.join(args.work, "paper.txt")
    if not os.path.isfile(paper):
        eprint("FATAL: %s missing; run extract first" % paper)
        return 3
    with open(paper, encoding="utf-8") as fh:
        text = fh.read()
    issues, warnings = [], []

    n_chars = len(text)
    stripped = text.strip()
    if n_chars == 0:
        issues.append("empty_text: extraction produced zero characters "
                      "(scanned PDF without text layer?)")
    repl = text.count(REPLACEMENT)
    if repl:
        warnings.append("encoding: %d U+FFFD replacement chars (decode loss)" % repl)

    sections = detect_sections(text)
    missing = [s for s, _ in CANONICAL_SECTIONS if s not in sections]
    if "abstract" not in sections and n_chars > 4000:
        warnings.append("no_abstract_heading: heading detection may have failed "
                        "or the text is truncated at the front")
    if "references" not in sections and n_chars > 4000:
        warnings.append("no_references_heading: text may be truncated at the end "
                        "or headings use non-canonical names")

    tail = stripped[-200:] if stripped else ""
    trunc_suspect = False
    if stripped:
        last = stripped[-1]
        if last not in ".。!！?？)]）】\"”*" and not stripped.endswith(" et al."):
            trunc_suspect = True
            warnings.append("abrupt_end: text ends mid-sentence (...%r); "
                            "suspect truncation" % tail[-40:])

    prof = line_profile(text)
    if prof["short_line_ratio"] > 0.85 and prof["nonempty_lines"] > 40:
        warnings.append("fragmented_lines: %.0f%% of lines <45 chars; possible "
                        "column interleave or OCR line splitting"
                        % (100 * prof["short_line_ratio"]))

    # crude column-interleave probe: many lines containing two wide gaps
    gap2 = sum(1 for ln in text.split("\n") if len(re.findall(r"\S {3,}\S.* {3,}\S", ln)) > 0)
    if gap2 > 0.4 * max(1, prof["nonempty_lines"]):
        warnings.append("column_interleave_suspect: >40%% of lines carry two wide "
                        "gaps; verify reading order against the rendered PDF")

    formfeeds = text.count("\f")
    page_est = formfeeds + 1 if formfeeds else None
    if n_chars > 0 and n_chars < 1500:
        warnings.append("very_short: %d chars total; is this the full paper?" % n_chars)

    if issues:
        gate, code = "fail", 3
    elif warnings:
        gate, code = "degraded", 2
    else:
        gate, code = "pass", 0

    cert = {
        "fidelity_gate": gate,
        "char_count": n_chars,
        "page_count_estimate": page_est,
        "sections_detected": sorted(sections, key=sections.get),
        "canonical_sections_missing": missing,
        "truncation_suspected": trunc_suspect,
        "line_profile": prof,
        "issues": issues,
        "warnings": warnings,
        "paper_sha256": sha256_file(paper),
        "obligations": ([
            "禁止宣称已完成全文审查；缺失/可疑部分必须列入 result.json 的未检查项",
            "每条 finding 的 quote 必须用 anchor 产物做逐字 quotecheck",
        ] if gate != "pass" else [
            "每条 finding 的 quote 必须用 anchor 产物做逐字 quotecheck",
        ]),
    }
    atomic_write_json(os.path.join(args.work, "fidelity_certificate.json"), cert)
    md = ["# 输入保真证书（fidelity certificate）", "",
          "- gate: **%s**" % gate,
          "- chars: %d；pages(估): %s" % (n_chars, page_est),
          "- sections: %s" % ", ".join(cert["sections_detected"]),
          "- missing: %s" % (", ".join(missing) if missing else "无"),
          "- truncation_suspected: %s" % trunc_suspect, ""]
    if warnings:
        md += ["## warnings"] + ["- %s" % w for w in warnings]
    if issues:
        md += ["## issues"] + ["- %s" % i for i in issues]
    atomic_write(os.path.join(args.work, "fidelity_certificate.md"), "\n".join(md) + "\n")
    print(json.dumps({"fidelity_gate": gate, "warnings": len(warnings),
                      "issues": len(issues)}, ensure_ascii=False))
    return code


# ------------------------------------------------------------------ anchor
# Sentence scanner: a period only terminates a sentence when it is not the
# decimal point inside a number (next char is not a digit). Otherwise p=0.03
# would be chopped at "0.". CJK full-width stops always terminate.
SENT = re.compile(r".*?(?:[。！？；;!?]+|(?<!\bal)\.+(?!\d)|\n|$)")


def cmd_anchor(args):
    paper = os.path.join(args.work, "paper.txt")
    if not os.path.isfile(paper):
        eprint("FATAL: %s missing; run extract first" % paper)
        return 3
    with open(paper, encoding="utf-8") as fh:
        text = fh.read()
    sections = detect_sections(text)
    bounds = sorted(sections.items(), key=lambda kv: kv[1])

    def section_at(pos):
        cur = "front_matter"
        for name, start in bounds:
            if pos >= start:
                cur = name
        return cur

    out = []
    idx = 0
    for m in SENT.finditer(text):
        s = m.group(0).strip()
        if not s or len(s) < 4:
            continue
        idx += 1
        out.append({"id": "S%04d" % idx,
                    "offset": m.start(),
                    "section": section_at(m.start()),
                    "text": s})
    path = os.path.join(args.work, "sentences.jsonl")
    atomic_write(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    meta = {"sentence_count": len(out), "paper_sha256": sha256_file(paper),
            "id_format": "S%04d, offsets are 0-based char offsets into paper.txt"}
    atomic_write_json(os.path.join(args.work, "anchor_meta.json"), meta)
    print(json.dumps({"status": "ok", "sentences": len(out)}, ensure_ascii=False))
    return 0


# -------------------------------------------------------------- quotecheck
def cmd_quotecheck(args):
    spath = os.path.join(args.work, "sentences.jsonl")
    if not os.path.isfile(spath):
        eprint("FATAL: sentences.jsonl missing; run anchor first")
        return 3
    sents = {}
    with open(spath, encoding="utf-8") as fh:
        for ln in fh:
            r = json.loads(ln)
            sents[r["id"]] = r["text"]
    with open(args.findings, encoding="utf-8") as fh:
        findings = json.load(fh)
    problems = []
    for f in findings:
        fid = f.get("id", "?")
        sid = f.get("sentence_id")
        q = f.get("quote", "")
        if sid not in sents:
            problems.append({"id": fid, "problem": "unknown sentence_id %r" % sid})
            continue
        if not q or q not in sents[sid]:
            near = ""
            # locate the closest sentence to help the fix
            for other_id, txt in sents.items():
                if q and q[:20] in txt:
                    near = " (quote fragment appears in %s instead)" % other_id
                    break
            problems.append({"id": fid,
                             "problem": "quote is not a verbatim substring of %s%s"
                                        % (sid, near)})
    if problems:
        atomic_write_json(os.path.join(args.work, "quotecheck_problems.json"), problems)
        for p in problems:
            eprint("VIOLATION %s: %s" % (p["id"], p["problem"]))
        return 4
    print(json.dumps({"status": "ok", "checked": len(findings)}, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract")
    p.add_argument("--input", required=True)
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_extract)
    p = sub.add_parser("certificate")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_certificate)
    p = sub.add_parser("anchor")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_anchor)
    p = sub.add_parser("quotecheck")
    p.add_argument("--work", required=True)
    p.add_argument("--findings", required=True)
    p.set_defaults(fn=cmd_quotecheck)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
