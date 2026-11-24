#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repair_apply.py — 审批制修复执行器（Python 3 标准库，确定性）。

读取经审批的 repair_map.json（suggested_repair_map.json 的审批副本）：
  - 校验 input_sha256 与输入文件实际哈希一致，不一致立即拒绝；
  - 仅执行 approved=true 的修复项；ambiguous=true 的项即使 approved 也会再次警告计数；
  - 每个操作记录 before/after 计数与受影响位置到 repair_log.json（可逆性凭据）；
  - 输出恢复表 recovered.csv（规范 CSV：逗号分隔、LF 行尾、UTF-8 无 BOM）。

绝不执行未批准项；绝不发明修复；token 级语义（缺失分类等）不在本层处理。
退出码：0 成功；2 参数错误；3 哈希不符；4 存在未批准项（拒绝执行）。
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys

FULLWIDTH_MAP = {}
for _i in range(10):
    FULLWIDTH_MAP[chr(ord("０") + _i)] = str(_i)
for _i in range(26):
    FULLWIDTH_MAP[chr(ord("Ａ") + _i)] = chr(ord("A") + _i)
    FULLWIDTH_MAP[chr(ord("ａ") + _i)] = chr(ord("a") + _i)
FULLWIDTH_MAP.update({"．": ".", "，": ",", "％": "%"})
INVISIBLE_CHARS = [" ", "​", "‌", "‍", "﻿", "　"]


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def apply_op(text, op, log):
    name = op["op"]
    if name == "decode":
        # decode 在读取阶段处理，此处仅记录
        log["note"] = "decode 操作在字节读取阶段已应用"
        return text
    if name == "strip_bom":
        before = 1 if text.startswith("﻿") else 0
        log["removed"] = before
        return text.lstrip("﻿")
    if name == "mojibake_fix":
        if op.get("via") != "latin1_utf8":
            raise ValueError("未知 mojibake 修复路径: %r" % op.get("via"))
        # 逐行修复：含 latin-1 不可编码字符（如后注入的全角数字）的行保持原样，
        # 行号写入日志，供核验与人工复核。
        lines = text.split("\n")
        repaired, skipped = [], []
        for i, line in enumerate(lines, 1):
            try:
                lines[i - 1] = line.encode("latin-1").decode("utf-8")
                if lines[i - 1] != line:
                    repaired.append(i)
            except (UnicodeEncodeError, UnicodeDecodeError):
                skipped.append(i)
        log["repaired_lines"] = repaired[:200]
        log["repaired_line_count"] = len(repaired)
        log["skipped_lines"] = skipped[:200]
        log["skipped_line_count"] = len(skipped)
        return "\n".join(lines)
    if name == "normalize_eol":
        to = {"\\n": "\n", "\\r\\n": "\r\n"}.get(op.get("to", "\\n"), "\n")
        before = text.count("\r\n") + text.count("\n") + text.count("\r")
        t = text.replace("\r\n", "\n").replace("\r", "\n")
        if to != "\n":
            t = t.replace("\n", to)
        log["linebreaks_normalized"] = before
        return t
    if name == "strip_invisible":
        removed = 0
        for ch in INVISIBLE_CHARS:
            n = text.count(ch)
            if n:
                removed += n
                text = text.replace(ch, " " if ch in (" ", "　") else "")
        log["removed_chars"] = removed
        return text
    if name == "fullwidth_to_ascii":
        n = 0
        out = []
        for ch in text:
            if ch in FULLWIDTH_MAP:
                out.append(FULLWIDTH_MAP[ch])
                n += 1
            else:
                out.append(ch)
        log["converted_chars"] = n
        return "".join(out)
    if name == "set_delimiter":
        # 结构操作：在序列化阶段处理
        log["note"] = "delimiter 在序列化阶段应用: %r" % op.get("delimiter")
        return text
    raise ValueError("未知操作: %r" % name)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="原始输入文件（与 repair_map.input_file 一致）")
    ap.add_argument("--map", dest="mapfile", required=True, help="经审批的 repair_map.json")
    ap.add_argument("--out", required=True, help="产物输出目录")
    args = ap.parse_args()

    repmap = json.load(open(args.mapfile, encoding="utf-8"))
    raw = open(args.file, "rb").read()
    actual = sha256_bytes(raw)
    if actual != repmap.get("input_sha256"):
        print("ERROR: 输入文件 sha256 与 repair_map 记录不符", file=sys.stderr)
        print("  实际: %s" % actual, file=sys.stderr)
        print("  记录: %s" % repmap.get("input_sha256"), file=sys.stderr)
        sys.exit(3)

    pending = [r for r in repmap["repairs"] if not r.get("approved")]
    if pending:
        print("ERROR: 存在未批准修复项，拒绝执行: %s"
              % ", ".join(r["id"] for r in pending), file=sys.stderr)
        sys.exit(4)

    # 读取阶段：decode 操作
    decode_op = next((r for r in repmap["repairs"] if r["op"]["op"] == "decode"), None)
    codec = decode_op["op"]["from"] if decode_op else "utf-8"
    text = raw.decode(codec)
    if not decode_op and text.startswith("﻿"):
        text = text.lstrip("﻿")

    os.makedirs(args.out, exist_ok=True)
    log = {"input_file": os.path.abspath(args.file), "input_sha256": actual,
           "applied": [], "warnings": []}
    delim_op = next((r for r in repmap["repairs"] if r["op"]["op"] == "set_delimiter"),
                    None)

    for r in repmap["repairs"]:
        op = r["op"]
        oplog = {"id": r["id"], "op": op, "score": r.get("score")}
        if r.get("ambiguous"):
            log["warnings"].append("%s 为歧义项，已经审批确认执行" % r["id"])
        text = apply_op(text, op, oplog)
        log["applied"].append(oplog)

    # 序列化阶段：按声明分隔符解析并重写为规范 CSV
    if delim_op:
        d = delim_op["op"]["delimiter"]
        rows = list(csv.reader(io.StringIO(text), delimiter=d))
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        for row in rows:
            w.writerow(row)
        text = buf.getvalue()
        log["delimiter_reserialized"] = {"from": d, "rows": len(rows)}

    if not text.endswith("\n"):
        text += "\n"
    out_csv = os.path.join(args.out, "recovered.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    log["output_file"] = os.path.abspath(out_csv)
    log["output_sha256"] = sha256_bytes(text.encode("utf-8"))
    with open(os.path.join(args.out, "repair_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": "ok", "applied": len(log["applied"]),
                      "warnings": len(log["warnings"]),
                      "output": log["output_file"],
                      "output_sha256": log["output_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
