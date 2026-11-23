#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_anchors.py — 锚定机检（anchor verification），自包含脚本。

对 agent 填写的比较矩阵单元格 cells.jsonl 做机器校验，每行一个单元格：
  {"field","value","status","source_document_id","paragraph_id","content_hash","quote"}
  status ∈ {reported, not_reported, unclear, conflict}

机检规则（任一失败即非零退出并打印失败清单）：
  R1  source_document_id 必须存在于 registry.json；
  R2  不得引用 identity_verdict ∈ {exact_duplicate, near_duplicate,
      probable_version_pair} 的非规范文档（只允许 canonical/unique 文档）；
  R3  不得引用 parse_fidelity ∈ {failed, tool_missing, unreadable} 的文档；
  R4  提供 --relevance 时，不得引用 out_of_scope 文档；
  R5  paragraph_id 必须存在于该文档的段落注册表；
  R6  cell 的 content_hash 必须与按注册段落文本重算的 hash 一致（防换版/伪造锚点）；
  R7  quote 必须逐字（exact substring）出现在所引段落文本中；
  R8  status=reported 必须带非空 value，且 value 中的每个数字都必须出现在 quote 中；
  R9  status=not_reported 不得携带 value。

用法：
  python3 verify_anchors.py --registry <dir-or-registry.json> --cells cells.jsonl \
      [--relevance relevance.json]
退出码：0 全部通过；1 存在失败项或用法/IO 错误。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata

BLOCKED_IDENTITY = {"exact_duplicate", "near_duplicate", "probable_version_pair"}
BLOCKED_PARSE = {"failed", "tool_missing", "unreadable"}
VALID_STATUS = {"reported", "not_reported", "unclear", "conflict"}
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^0-9a-z一-鿿]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text):
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:12]


def load_paragraphs(registry_dir, doc):
    pf = os.path.join(registry_dir, doc.get("paragraphs_file", ""))
    paras = {}
    if os.path.isfile(pf):
        with open(pf, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                paras[rec["paragraph_id"]] = rec
    return paras


def main(argv=None):
    ap = argparse.ArgumentParser(description="机检比较矩阵单元格的引用锚点")
    ap.add_argument("--registry", required=True, help="registry.json 或其所在目录")
    ap.add_argument("--cells", required=True, help="cells.jsonl（每行一个单元格）")
    ap.add_argument("--relevance", default=None, help="relevance.json（可选，启用 R4）")
    args = ap.parse_args(argv)

    reg_path = args.registry
    if os.path.isdir(reg_path):
        reg_path = os.path.join(reg_path, "registry.json")
    try:
        with open(reg_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("error: cannot load registry: %s" % e, file=sys.stderr)
        return 1
    registry_dir = os.path.dirname(os.path.abspath(reg_path))
    docs = {d["doc_id"]: d for d in registry.get("documents", [])}
    para_cache = {}

    rel_map = {}
    if args.relevance:
        try:
            with open(args.relevance, "r", encoding="utf-8") as f:
                rel = json.load(f)
            rel_map = {d["doc_id"]: d.get("verdict") for d in rel.get("documents", [])}
        except (OSError, json.JSONDecodeError) as e:
            print("error: cannot load relevance: %s" % e, file=sys.stderr)
            return 1

    cells = []
    try:
        with open(args.cells, "r", encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    cells.append((ln, json.loads(line)))
                except json.JSONDecodeError as e:
                    print("FAIL line %d: invalid JSON: %s" % (ln, e))
                    return 1
    except OSError as e:
        print("error: cannot read cells: %s" % e, file=sys.stderr)
        return 1

    failures = []
    n_pass = 0

    def fail(ln, cell, rule, msg):
        failures.append({"line": ln, "rule": rule,
                         "cell": {k: cell.get(k) for k in
                                  ("field", "source_document_id", "paragraph_id")},
                         "message": msg})

    for ln, cell in cells:
        ok = True
        doc_id = cell.get("source_document_id")
        pid = cell.get("paragraph_id")
        status = cell.get("status")
        value = cell.get("value")
        quote = cell.get("quote")
        chash = cell.get("content_hash")

        if status not in VALID_STATUS:
            fail(ln, cell, "R0", "status must be one of %s, got %r" % (sorted(VALID_STATUS), status))
            ok = False

        # R1
        doc = docs.get(doc_id)
        if doc is None:
            fail(ln, cell, "R1", "source_document_id %r not in registry" % doc_id)
            ok = False
        else:
            # R2
            iv = doc.get("identity_verdict")
            if iv in BLOCKED_IDENTITY:
                fail(ln, cell, "R2", "doc %s has identity_verdict=%s (non-canonical: %s); "
                     "cite the canonical document instead"
                     % (doc_id, iv, doc.get("identity_evidence", {}).get("related_to")))
                ok = False
            # R3
            pf = doc.get("parse_fidelity")
            if pf in BLOCKED_PARSE:
                fail(ln, cell, "R3", "doc %s parse_fidelity=%s; extraction forbidden" % (doc_id, pf))
                ok = False
            # R4
            if rel_map and rel_map.get(doc_id) == "out_of_scope":
                fail(ln, cell, "R4", "doc %s is out_of_scope per relevance gate" % doc_id)
                ok = False
            # R5/R6/R7
            if doc_id not in para_cache:
                para_cache[doc_id] = load_paragraphs(registry_dir, doc)
            paras = para_cache[doc_id]
            prec = paras.get(pid)
            if prec is None:
                fail(ln, cell, "R5", "paragraph_id %r not registered for doc %s" % (pid, doc_id))
                ok = False
            else:
                recomputed = content_hash(prec.get("text", ""))
                if recomputed != prec.get("content_hash"):
                    fail(ln, cell, "R6", "registry paragraph %s hash mismatch (registry=%s, "
                         "recomputed=%s): corpus may have been swapped"
                         % (pid, prec.get("content_hash"), recomputed))
                    ok = False
                if chash != prec.get("content_hash"):
                    fail(ln, cell, "R6", "cell content_hash %r != registry %r for %s"
                         % (chash, prec.get("content_hash"), pid))
                    ok = False
                if quote is not None:
                    if not isinstance(quote, str) or not quote.strip():
                        fail(ln, cell, "R7", "quote is empty")
                        ok = False
                    elif quote not in prec.get("text", ""):
                        fail(ln, cell, "R7", "quote is not a verbatim substring of %s" % pid)
                        ok = False

        # R8
        if status == "reported":
            if value is None or (isinstance(value, str) and not value.strip()):
                fail(ln, cell, "R8", "status=reported requires a non-empty value")
                ok = False
            elif quote and doc_id in docs:
                nums = NUMBER_RE.findall(str(value))
                missing = [n for n in nums if n not in str(quote)]
                if missing:
                    fail(ln, cell, "R8", "value numbers %s not found in quote" % missing)
                    ok = False
            if not quote:
                fail(ln, cell, "R8", "status=reported requires a quote anchor")
                ok = False
        # R9
        if status == "not_reported":
            if value is not None and not (isinstance(value, str) and not value.strip()):
                fail(ln, cell, "R9", "status=not_reported must not carry a value, got %r" % value)
                ok = False

        if ok:
            n_pass += 1
            print("PASS line %-3d  %-22s %-10s %-14s %-10s"
                  % (ln, cell.get("field"), doc_id, pid, status))
        else:
            print("FAIL line %-3d  %-22s %-10s %-14s %-10s"
                  % (ln, cell.get("field"), doc_id, pid, status))

    print("-" * 72)
    print("verify_anchors: %d/%d cells passed" % (n_pass, len(cells)))
    if failures:
        print("FAILURE LIST:")
        for f in failures:
            print("  [line %d][%s] %s :: %s" % (f["line"], f["rule"], f["cell"], f["message"]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
