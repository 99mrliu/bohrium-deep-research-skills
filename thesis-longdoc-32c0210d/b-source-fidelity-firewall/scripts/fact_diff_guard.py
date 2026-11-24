#!/usr/bin/env python3
"""fact_diff_guard.py — 编辑后事实保真把关，产出 guard_report.json。

两道闸：
  A. fabrication_token：改后文本中的每个数字 token、全大写缩写、[n] 引文，
     若既不出现在改前文本、也不出现在材料文本、也不被 evidence_map 覆盖
     → flag。
  B. unverified_new_sentence：改后新增的（改前不存在的）含数字/引文的句子，
     其每个数字/引文 token 必须能在 evidence_map 的 claim/quote/value 语料中
     找到对应，否则 flag。

有任何 flag → 退出码 1；全部通过 → 退出码 0。

用法：
  python3 fact_diff_guard.py --before <改前章节目录> --after <改后章节目录> \
      --evidence evidence_map.json --out guard_report.json [--materials <目录>]
"""
import argparse
import json
import os
import re
import sys

RE_WS = re.compile(r"\s+")
RE_NUM = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])")
RE_ABBR = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,9}(?![A-Za-z0-9])")
RE_CIT = re.compile(r"\[\d{1,3}\]")
RE_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+")


def norm(text):
    return RE_WS.sub(" ", text).strip()


def read_dir_texts(root, exts=(".md", ".txt")):
    """返回 {rel: text}，排序确定。"""
    texts = {}
    if not root or not os.path.isdir(root):
        return texts
    for r, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            if name.lower().endswith(exts):
                path = os.path.join(r, name)
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    texts[os.path.relpath(path, root)] = fh.read()
    return dict(sorted(texts.items()))


def tokens_of(text):
    return {
        "number": set(RE_NUM.findall(text)),
        "abbreviation": set(RE_ABBR.findall(text)),
        "citation": set(RE_CIT.findall(text)),
    }


def token_in_text(kind, token, text):
    if kind == "number":
        return re.search(r"(?<![\d.])%s(?![\d.])" % re.escape(token), text) is not None
    if kind == "citation":
        return token in text
    return re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])"
                     % re.escape(token), text) is not None


def evidence_corpus(evidence_doc):
    parts = []
    for e in evidence_doc.get("entries", []):
        parts.append(e.get("claim") or "")
        parts.append(e.get("value") or "")
        for ev in e.get("evidence", []):
            parts.append(ev.get("quote") or "")
    return "\n".join(parts)


def sentences_of(text):
    out = []
    for line in text.splitlines():
        for seg in RE_SENT_SPLIT.split(line):
            seg = (seg or "").strip()
            if seg:
                out.append(seg)
    return out


def main():
    ap = argparse.ArgumentParser(description="编辑后事实保真把关 → guard_report.json")
    ap.add_argument("--before", required=True, help="改前章节目录")
    ap.add_argument("--after", required=True, help="改后章节目录")
    ap.add_argument("--evidence", required=True, help="evidence_map.json")
    ap.add_argument("--materials", default=None, help="材料目录（可选）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    before = read_dir_texts(args.before)
    after = read_dir_texts(args.after)
    materials = read_dir_texts(args.materials) if args.materials else {}
    with open(args.evidence, "r", encoding="utf-8") as fh:
        evidence_doc = json.load(fh)
    ev_corpus = evidence_corpus(evidence_doc)

    allowed_text = "\n".join(list(before.values()) + list(materials.values()))
    flags = []
    checked = {"number": 0, "abbreviation": 0, "citation": 0,
               "new_sentences": 0}

    after_all = "\n".join(after.values())
    after_tokens = tokens_of(after_all)
    before_norm = norm("\n".join(before.values()))

    # 闸 A：token 级
    for kind in ("number", "abbreviation", "citation"):
        for tok in sorted(after_tokens[kind]):
            checked[kind] += 1
            in_allowed = token_in_text(kind, tok, allowed_text)
            in_evidence = token_in_text(kind, tok, ev_corpus)
            if not in_allowed and not in_evidence:
                flags.append({
                    "type": "fabrication_token",
                    "token_kind": kind,
                    "token": tok,
                    "detail": "改后文本中的 %s token %r 既不在改前文本、"
                              "也不在材料中，且未被 evidence_map 覆盖"
                              % (kind, tok),
                })

    # 闸 B：新增句子级
    for rel, text in after.items():
        for sent in sentences_of(text):
            nsent = norm(sent)
            if nsent in before_norm:
                continue
            if not (RE_NUM.search(sent) or RE_CIT.search(sent)):
                continue
            checked["new_sentences"] += 1
            missing = []
            for tok in set(RE_NUM.findall(sent)):
                if not token_in_text("number", tok, ev_corpus):
                    missing.append(tok)
            for tok in set(RE_CIT.findall(sent)):
                if tok not in ev_corpus:
                    missing.append(tok)
            if missing:
                flags.append({
                    "type": "unverified_new_sentence",
                    "file": rel,
                    "sentence": sent,
                    "missing_tokens": sorted(missing),
                    "detail": "新增句子含未被 evidence_map 覆盖的 token：%s"
                              % ", ".join(sorted(missing)),
                })

    report = {
        "schema": "guard_report/v1",
        "status": "FAIL" if flags else "PASS",
        "summary": {
            "before_files": len(before),
            "after_files": len(after),
            "materials_files": len(materials),
            "tokens_checked": checked,
            "flags": len(flags),
        },
        "flags": flags,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("fact_diff_guard: %s, %d flag(s) -> %s"
          % (report["status"], len(flags), args.out))
    for f in flags:
        print("FLAG[%s]: %s" % (f["type"], f["detail"]), file=sys.stderr)
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main())
