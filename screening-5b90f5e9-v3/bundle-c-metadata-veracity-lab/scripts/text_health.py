#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""text_health.py — 编码与文本健康检查 + 可安全修复（留痕）

检测三类典型毛病（详见 references/encoding_and_identifier_notes.md）：
  1. mojibake / 乱码：UTF-8 字节被按 Latin-1 解码的典型模式（"Ã©"、"â€™" 等）
  2. HTML 实体残留：&amp; &#233; &eacute; 等
  3. 控制字符 / 零宽字符 / 内嵌 BOM

处置原则（保守）：
  * 可安全修复（修复后可验证：可疑模式数下降、不引入 U+FFFD）→ 修复并逐条留痕
  * 无法安全修复（混合编码、修复校验失败）→ 保留原值，标记 untrusted，绝不猜改
  * 只动文本字段（title/abstract/journal/keywords 等），不动标识符字段

退出码：0 成功（含"无问题"）；2 运行/IO 错误；3 输入合同不满足。
幂等：输出文件整体重写；对已修复文本再跑不会产生二次改动（修复是幂等的）。
"""
import argparse
import html
import json
import os
import re
import sys

TEXT_FIELDS_DEFAULT = ["title", "abstract", "journal", "source", "keywords",
                       "publication_type"]

# UTF-8 按 Latin-1 误读的高频指纹：\u00c3/\u00c2 + 续字节，\u00e2xx 型
# 三字节序列（如 â€™），\u00f0xxx 型 emoji 残骸，以及替换符 U+FFFD。
MOJIBAKE_RE = re.compile(
    "(?:\\u00c3[\\u0080-\\u00bf]|\\u00c2[\\u0080-\\u00bf]"
    "|\\u00e2[\\u0080-\\u00bf]{2}|\\u00f0[\\u0080-\\u00bf]{3}|\\ufffd)")
# 控制字符（保留 \t \n \r）与 DEL
CONTROL_RE = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]")
# 零宽字符与 BOM（出现在字段中部即视为残留）
INVISIBLE_RE = re.compile("[\\ufeff\\u200b\\u200c\\u200d]")
ENTITY_RE = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);")
# 非 ASCII 的 Latin-1 区间字符簇（用于整串修复失败后的局部修复）
CLUSTER_RE = re.compile("[\\u0080-\\u00ff]{2,}")


def suspicious_count(text):
    return len(MOJIBAKE_RE.findall(text))


def try_fix_mojibake(text):
    """尝试把"UTF-8 被当 Latin-1 读"的文本还原。

    先整串 round-trip；失败则只对 Latin-1 区间的字符簇逐个 round-trip。
    接受条件：可疑模式数严格下降 且 不引入替换符 U+FFFD。否则返回 None。
    """
    before = suspicious_count(text)
    if before == 0:
        return None
    # 路径 A：整串可 Latin-1 编码（纯拉丁脚本乱码的最常见情形）
    try:
        fixed = text.encode("latin-1").decode("utf-8")
        if fixed != text and "�" not in fixed and \
                suspicious_count(fixed) < before:
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    # 路径 B：逐簇修复（合法非 ASCII 字符与乱码混杂的情形）
    changed = [False]

    def _fix_cluster(match):
        chunk = match.group(0)
        try:
            fixed = chunk.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return chunk
        if "�" in fixed:
            return chunk
        changed[0] = True
        return fixed

    candidate = CLUSTER_RE.sub(_fix_cluster, text)
    if changed[0] and suspicious_count(candidate) < before and \
            "�" not in candidate:
        return candidate
    return None


def scan_and_repair(records, text_fields):
    """返回 (修复后记录, 报告)。报告含 issues 与 changes（留痕）。"""
    fixed_records = []
    issues = []
    changes = []
    for rec in records:
        rid = rec["record_id"]
        rec = dict(rec)
        for field in text_fields:
            if field not in rec:
                continue
            value = rec[field]
            items = value if isinstance(value, list) else [value]
            if not all(isinstance(x, str) for x in items):
                continue
            new_items = []
            for item in items:
                original = item
                current = item
                # 1) 控制字符 / 不可见字符：删除即安全
                stripped = CONTROL_RE.sub("", current)
                stripped = INVISIBLE_RE.sub("", stripped)
                if stripped != current:
                    issues.append({"record_id": rid, "field": field,
                                   "issue": "control_or_invisible_chars",
                                   "action": "repaired"})
                    current = stripped
                # 2) mojibake
                if suspicious_count(current) > 0:
                    fixed = try_fix_mojibake(current)
                    if fixed is not None:
                        issues.append({"record_id": rid, "field": field,
                                       "issue": "mojibake_utf8_as_latin1",
                                       "action": "repaired"})
                        current = fixed
                    else:
                        issues.append({"record_id": rid, "field": field,
                                       "issue": "mojibake_unrepairable",
                                       "action": "flagged_untrusted"})
                # 3) HTML 实体残留
                if ENTITY_RE.search(current):
                    unescaped = html.unescape(current)
                    if unescaped != current:
                        issues.append({"record_id": rid, "field": field,
                                       "issue": "html_entity_residue",
                                       "action": "repaired"})
                        current = unescaped
                if current != original:
                    changes.append({
                        "record_id": rid, "field": field,
                        "old": original, "new": current,
                        "source_record_id": None,
                        "rule": "text_health_safe_repair",
                    })
                new_items.append(current)
            rec[field] = new_items if isinstance(value, list) else new_items[0]
        fixed_records.append(rec)
    report = {
        "generated_by": "text_health.py",
        "records_total": len(records),
        "fields_scanned": text_fields,
        "issues": issues,
        "changes": changes,
        "untrusted_text_fields": sorted({
            "%s.%s" % (i["record_id"], i["field"])
            for i in issues if i["action"] == "flagged_untrusted"}),
        "notes": ["仅执行可验证的安全修复；不可修复的乱码保留原值并标记，",
                   "不做任何猜测性改写。"],
    }
    return fixed_records, report


def main(argv=None):
    parser = argparse.ArgumentParser(description="编码与文本健康检查 + 安全修复")
    parser.add_argument("--records", required=True, help="题录文件（JSONL 或 JSON）")
    parser.add_argument("--work", default="/app/work", help="中间产物目录")
    parser.add_argument("--text-fields", default=",".join(TEXT_FIELDS_DEFAULT),
                        help="逗号分隔的待扫描文本字段")
    args = parser.parse_args(argv)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from profile_fields import load_records  # 复用同一加载器，行为一致
        records = load_records(args.records)
        if not records:
            print("ERROR: 记录为空", file=sys.stderr)
            return 3
        text_fields = [f.strip() for f in args.text_fields.split(",") if f.strip()]
        fixed, report = scan_and_repair(records, text_fields)
        os.makedirs(args.work, exist_ok=True)
        rec_path = args.work.rstrip("/") + "/records_text_fixed.jsonl"
        rep_path = args.work.rstrip("/") + "/text_health_report.json"
        with open(rec_path, "w", encoding="utf-8") as fh:
            for rec in fixed:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with open(rep_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        print("OK: %d 条记录；issues=%d，修复留痕=%d，不可修复=%d -> %s, %s"
              % (len(fixed), len(report["issues"]), len(report["changes"]),
                 len(report["untrusted_text_fields"]), rec_path, rep_path))
        return 0
    except FileNotFoundError as exc:
        print("ERROR: 输入文件不存在: %s" % exc, file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # 顶层兜底：绝不以 traceback 崩溃退出
        print("ERROR: 未预期异常: %r" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
