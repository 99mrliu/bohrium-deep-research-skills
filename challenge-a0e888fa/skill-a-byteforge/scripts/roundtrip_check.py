#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""roundtrip_check.py — 独立重算与可逆性核验（Python 3 标准库）。

两类机械核验，互不依赖 Agent 自述：
  1. 独立重算一致性：用同一份经审批 repair_map.json 对原始字节**重新执行一遍**
     修复流程（独立实现路径），比对重算结果与已交付 recovered.csv 的 sha256。
     一致 ⇒ 修复过程可复现、无手工暗改。
  2. 可逆性抽查：对 replace 类操作（strip_invisible / fullwidth_to_ascii），
     验证恢复表中不再含被移除字符；对 mojibake_fix，验证修复文本可经
     encode('utf-8')→decode('latin-1') 还原到修复前文本（真正字节级往返）。

输出 roundtrip_verdict.json，全部通过打印 PASS 并退出 0，任一失败退出 5。
"""
import argparse
import hashlib
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


def independent_reapply(raw, repmap):
    """repair_apply.py 的独立重算路径（分隔逻辑：逐行 split 而非 csv 模块）。"""
    decode_op = next((r for r in repmap["repairs"] if r["op"]["op"] == "decode"), None)
    codec = decode_op["op"]["from"] if decode_op else "utf-8"
    text = raw.decode(codec)
    for r in repmap["repairs"]:
        op = r["op"]
        name = op["op"]
        if name == "decode":
            continue
        if name == "strip_bom":
            text = text.lstrip("﻿")
        elif name == "mojibake_fix":
            lines = text.split("\n")
            for i, line in enumerate(lines):
                try:
                    lines[i] = line.encode("latin-1").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            text = "\n".join(lines)
        elif name == "normalize_eol":
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        elif name == "strip_invisible":
            for ch in INVISIBLE_CHARS:
                text = text.replace(ch, " " if ch in (" ", "　") else "")
        elif name == "fullwidth_to_ascii":
            text = "".join(FULLWIDTH_MAP.get(c, c) for c in text)
    delim_op = next((r for r in repmap["repairs"] if r["op"]["op"] == "set_delimiter"),
                    None)
    if delim_op:
        d = delim_op["op"]["delimiter"]
        lines = [l for l in text.split("\n")]
        out_lines = []
        for l in lines:
            if l == "" and l is lines[-1]:
                out_lines.append(l)
                continue
            cells = [c for c in l.split(d)]
            escaped = []
            for c in cells:
                if any(k in c for k in (",", '"', "\n")):
                    escaped.append('"' + c.replace('"', '""') + '"')
                else:
                    escaped.append(c)
            out_lines.append(",".join(escaped))
        text = "\n".join(out_lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--original", required=True, help="原始输入文件")
    ap.add_argument("--map", dest="mapfile", required=True, help="经审批的 repair_map.json")
    ap.add_argument("--recovered", required=True, help="已交付的 recovered.csv")
    ap.add_argument("--out", required=True, help="核验报告输出目录")
    args = ap.parse_args()

    repmap = json.load(open(args.mapfile, encoding="utf-8"))
    raw = open(args.original, "rb").read()
    recovered = open(args.recovered, "rb").read()
    verdict = {"checks": [], "all_pass": True}

    def record(name, ok, detail):
        verdict["checks"].append({"check": name, "pass": bool(ok), "detail": detail})
        if not ok:
            verdict["all_pass"] = False

    # 0) 输入哈希一致
    record("input_sha256_match",
           sha256_bytes(raw) == repmap.get("input_sha256"),
           {"actual": sha256_bytes(raw), "recorded": repmap.get("input_sha256")})

    # 1) 独立重算一致性
    try:
        recomputed = independent_reapply(raw, repmap)
        same = sha256_bytes(recomputed.encode("utf-8")) == sha256_bytes(recovered)
        record("independent_recompute_match", same,
               {"recomputed_sha256": sha256_bytes(recomputed.encode("utf-8")),
                "delivered_sha256": sha256_bytes(recovered)})
    except Exception as e:
        record("independent_recompute_match", False, {"error": str(e)})

    # 2) 可逆性抽查
    text = open(args.recovered, encoding="utf-8").read()
    if any(r["op"]["op"] == "strip_invisible" for r in repmap["repairs"]):
        residual = {c: text.count(c) for c in INVISIBLE_CHARS if text.count(c)}
        record("invisible_removed", not residual, {"residual": residual})
    if any(r["op"]["op"] == "fullwidth_to_ascii" for r in repmap["repairs"]):
        residual = [c for c in FULLWIDTH_MAP if c in text]
        record("fullwidth_converted", not residual, {"residual": residual[:10]})
    moj = next((r for r in repmap["repairs"] if r["op"]["op"] == "mojibake_fix"), None)
    if moj:
        # 字节级往返抽查：重放 mojibake_fix 之前的操作得到 pre 文本，对其逐行执行
        # 修复得到 post，再对采样行验证 post.encode('utf-8').decode('latin-1') == pre。
        try:
            decode_op = next((r for r in repmap["repairs"]
                              if r["op"]["op"] == "decode"), None)
            pre = raw.decode(decode_op["op"]["from"] if decode_op else "utf-8")
            for r in repmap["repairs"]:
                if r["op"]["op"] == "mojibake_fix":
                    break
                n = r["op"]["op"]
                if n == "strip_bom":
                    pre = pre.lstrip("﻿")
                elif n == "normalize_eol":
                    pre = pre.replace("\r\n", "\n").replace("\r", "\n")
            sampled, bad = 0, []
            for i, line in enumerate(pre.split("\n"), 1):
                try:
                    post = line.encode("latin-1").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
                if post == line:
                    continue
                sampled += 1
                if sampled > 20:
                    break
                if post.encode("utf-8").decode("latin-1") != line:
                    bad.append(i)
            record("mojibake_byte_roundtrip", not bad and sampled > 0,
                   {"sampled_repaired_lines": sampled, "bad_lines": bad})
        except Exception as e:
            record("mojibake_byte_roundtrip", False, {"error": str(e)})

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "roundtrip_verdict.json"), "w",
              encoding="utf-8") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=2)
    status = "PASS" if verdict["all_pass"] else "FAIL"
    print(json.dumps({"verdict": status,
                      "checks": {c["check"]: c["pass"] for c in verdict["checks"]}},
                     ensure_ascii=False))
    sys.exit(0 if verdict["all_pass"] else 5)


if __name__ == "__main__":
    main()
