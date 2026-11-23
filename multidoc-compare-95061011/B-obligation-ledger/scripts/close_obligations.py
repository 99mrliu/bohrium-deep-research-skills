#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""close_obligations.py — 校验 closures.jsonl 并按状态机判据合并回 obligations.jsonl。

agent 把填写结果写成 closures.jsonl，每条记录字段：
  obligation_id            必填，必须存在于 obligations.jsonl
  status                   必填，∈ {answered_with_evidence, not_reported_confirmed,
                                 conflict_preserved, out_of_scope}
  value / unit             answered 时 value 必填
  source_document_id, paragraph_id, quote   证据定位；quote 会逐字核验
  secondary_source_document_id, secondary_paragraph_id, secondary_quote  冲突时双方证据
  search_scope             已检索段落 id 列表（not_reported_confirmed 必填）
  note                     说明文字

语料段落索引由 --corpus 构建：目录（全部 *.jsonl）或单个 .jsonl 文件，
每行 {"document_id":..., "paragraph_id":..., "text":...}。

任何校验失败都不写回、以非零退出，保证义务不得静默消失、证据必须落地。
"""
import argparse
import glob
import json
import os
import sys

CLOSED_STATUSES = ("answered_with_evidence", "not_reported_confirmed", "conflict_preserved", "out_of_scope")


def load_jsonl(path):
    recs = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                print("[close] 错误：%s 第 %d 行不是合法 JSON：%s" % (path, i, e), file=sys.stderr)
                sys.exit(2)
    return recs


def build_index(corpus):
    """返回 {(document_id, paragraph_id): text}。"""
    idx = {}
    files = []
    if os.path.isdir(corpus):
        files = sorted(glob.glob(os.path.join(corpus, "*.jsonl")))
        files += sorted(glob.glob(os.path.join(corpus, "**", "*.jsonl"), recursive=True))
        files = sorted(set(files))
    elif os.path.isfile(corpus):
        files = [corpus]
    else:
        print("[close] 错误：--corpus 既不是目录也不是文件：%s" % corpus, file=sys.stderr)
        sys.exit(2)
    for fp in files:
        for rec in load_jsonl(fp):
            doc, pid, text = rec.get("document_id"), rec.get("paragraph_id"), rec.get("text")
            if doc and pid and text:
                idx[(str(doc), str(pid))] = str(text)
    if not idx:
        print("[close] 错误：语料 %s 中未找到任何 (document_id, paragraph_id, text) 段落记录" % corpus, file=sys.stderr)
        sys.exit(2)
    return idx


def check_quote(idx, errors, ctx, doc, pid, quote):
    if not doc or not pid:
        errors.append("%s：缺少 source_document_id/paragraph_id" % ctx)
        return
    if (doc, pid) not in idx:
        errors.append("%s：段落索引中不存在 (%s, %s)" % (ctx, doc, pid))
        return
    if quote is None or str(quote).strip() == "":
        errors.append("%s：quote 为空" % ctx)
        return
    if str(quote) not in idx[(doc, pid)]:
        errors.append("%s：quote 未逐字出现在 %s-%s 中（逐字核验失败）" % (ctx, doc, pid))


def validate_closure(rec, obl, idx):
    errors = []
    ctx = "obligation %s" % rec.get("obligation_id", "?")
    status = rec.get("status")
    if status not in CLOSED_STATUSES:
        errors.append("%s：status=%r 非法（须为 %s）" % (ctx, status, CLOSED_STATUSES))
        return errors
    scope_docs = []
    if obl.get("kind") == "field_cell":
        scope_docs = [obl.get("document_id")]
    elif obl.get("kind") == "comparability":
        scope_docs = list(obl.get("doc_pair") or [])

    if status == "answered_with_evidence":
        if not str(rec.get("value", "")).strip():
            errors.append("%s：answered_with_evidence 必须给出 value" % ctx)
        check_quote(idx, errors, ctx,
                    rec.get("source_document_id"), rec.get("paragraph_id"), rec.get("quote"))
        if scope_docs and rec.get("source_document_id") and rec.get("source_document_id") not in scope_docs:
            errors.append("%s：证据文档 %s 不在该义务管辖范围 %s 内" % (ctx, rec.get("source_document_id"), scope_docs))
    elif status == "not_reported_confirmed":
        scope = rec.get("search_scope")
        if not isinstance(scope, list) or not scope:
            errors.append("%s：not_reported_confirmed 必须给出 search_scope（已检索段落 id 列表）" % ctx)
        else:
            for pid in scope:
                hit = None
                for d in scope_docs:
                    if (d, str(pid)) in idx:
                        hit = (d, str(pid))
                        break
                if hit is None:
                    errors.append("%s：search_scope 中的段落 %s 不存在于管辖文档 %s" % (ctx, pid, scope_docs))
        if len(str(rec.get("note", "")).strip()) < 10:
            errors.append("%s：not_reported_confirmed 的 note 必须说明检索范围与结论（≥10 字符）" % ctx)
    elif status == "conflict_preserved":
        if not str(rec.get("value", "")).strip() and len(str(rec.get("note", "")).strip()) < 10:
            errors.append("%s：conflict_preserved 必须给出冲突描述（value 或 note）" % ctx)
        check_quote(idx, errors, ctx,
                    rec.get("source_document_id"), rec.get("paragraph_id"), rec.get("quote"))
        check_quote(idx, errors, ctx + "（对方证据）",
                    rec.get("secondary_source_document_id"), rec.get("secondary_paragraph_id"),
                    rec.get("secondary_quote"))
    elif status == "out_of_scope":
        if len(str(rec.get("note", "")).strip()) < 10:
            errors.append("%s：out_of_scope 必须在 note 中说明理由（≥10 字符）" % ctx)
    return errors


def main():
    ap = argparse.ArgumentParser(description="校验并合并 closures.jsonl 回 obligations.jsonl")
    ap.add_argument("--obligations", required=True, help="obligations.jsonl 路径")
    ap.add_argument("--closures", required=True, help="agent 填写的 closures.jsonl 路径")
    ap.add_argument("--corpus", required=True, help="语料目录或段落 jsonl 文件")
    ap.add_argument("--out", default=None, help="写回路径（默认原地覆盖 --obligations）")
    args = ap.parse_args()

    obligations = load_jsonl(args.obligations)
    by_id = {o["obligation_id"]: o for o in obligations}
    idx = build_index(args.corpus)
    print("[close] 段落索引 %d 段（来自 %s）" % (len(idx), args.corpus))

    closures = load_jsonl(args.closures)
    errors = []
    seen = {}
    for n, rec in enumerate(closures, 1):
        if not isinstance(rec, dict) or "obligation_id" not in rec:
            errors.append("第 %d 条 closure 缺少 obligation_id" % n)
            continue
        oid = str(rec["obligation_id"])
        if oid not in by_id:
            errors.append("closure #%d：obligation_id=%s 不存在于台账" % (n, oid))
            continue
        if oid in seen:
            print("[close] 警告：%s 重复关闭，后写覆盖先写" % oid, file=sys.stderr)
        seen[oid] = rec
        errors.extend(validate_closure(rec, by_id[oid], idx))

    if errors:
        print("[close] 校验失败 %d 处，未写回：" % len(errors), file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        sys.exit(1)

    for oid, rec in seen.items():
        by_id[oid]["status"] = rec["status"]
        by_id[oid]["closure"] = {k: v for k, v in rec.items() if k != "obligation_id"}

    out_path = args.out or args.obligations
    with open(out_path, "w", encoding="utf-8") as f:
        for o in obligations:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    closed = sum(1 for o in obligations if o["status"] != "open")
    by_status = {}
    for o in obligations:
        if o["status"] != "open":
            by_status[o["status"]] = by_status.get(o["status"], 0) + 1
    print("[close] 合并 %d/%d 条关闭记录 -> %s" % (len(seen), len(obligations), out_path))
    print("[close] 关闭 %d/%d（按状态：%s）；仍 open：%d" % (closed, len(obligations), by_status, len(obligations) - closed))


if __name__ == "__main__":
    main()
