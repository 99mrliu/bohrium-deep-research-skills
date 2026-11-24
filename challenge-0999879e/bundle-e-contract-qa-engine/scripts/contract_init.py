#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_init.py — 契约驱动的审查初始化（第 1 步，必须最先调用）。

职责：
1. 宽容解析 /input/case.json：
   - output_contract 为字段名 list 或 dict 均可；
   - 缺 case_id → 报错退出（退出码 2）；
   - schema 完全不识别 → 回退默认字段集并记入 uncertainty。
2. 抽取 /input 下全部材料文本（md/txt/tex 直读；pdf 尝试 pdftotext；
   docx 尝试 zipfile 提取；失败如实记录 extract_error），写入 work/。
3. 生成 work/answer_sheet.json 答题纸骨架（每个契约字段一格，含填写状态；
   另含六分面 facet_coverage 待填区）。
4. 第一次调用就原子写入保底 partial result.json 到输出目录。

仅使用 Python 3 标准库。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

DEFAULT_CONTRACT = ["case_id", "status", "review_report", "findings",
                    "sources", "uncertainty", "change_log"]
FACETS = ["事实核验", "引用支持", "方法设计", "统计报告", "论证链", "学术规范"]
TEXT_SUFFIXES = {".md", ".txt", ".tex"}


def eprint(*a):
    print(*a, file=sys.stderr)


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_contract(case, uncertainty):
    """宽容解析 output_contract，返回 (fields, fell_back)。"""
    oc = case.get("output_contract")
    if isinstance(oc, list) and oc and all(isinstance(x, str) and x.strip() for x in oc):
        return [x.strip() for x in oc], False
    if isinstance(oc, dict) and oc and all(isinstance(k, str) and k.strip() for k in oc):
        return [k.strip() for k in oc.keys()], False
    uncertainty.append(
        "output_contract 缺失或无法识别（应为字段名 list 或 dict），"
        "已回退默认字段集 " + json.dumps(DEFAULT_CONTRACT, ensure_ascii=False))
    return list(DEFAULT_CONTRACT), True


def extract_docx(path):
    """尽力用 zipfile 抽取 docx 正文；失败返回 None。"""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    except Exception:
        return None


def extract_inputs(input_dir):
    """返回 (entries, errors)。entries: [{file, sha256, chars}]；同时拼出全文。"""
    entries, errors, corpus_parts = [], [], []
    if not os.path.isdir(input_dir):
        return [], ["输入目录不存在: " + input_dir], ""
    for name in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path):
            continue
        suffix = os.path.splitext(name)[1].lower()
        if name in ("case.json",) or suffix == ".json":
            continue
        text, err = None, None
        if suffix in TEXT_SUFFIXES:
            text = read_text(path)
        elif suffix == ".pdf":
            tool = shutil.which("pdftotext")
            if tool:
                try:
                    r = subprocess.run([tool, "-enc", "UTF-8", path, "-"],
                                       capture_output=True, timeout=120)
                    if r.returncode == 0:
                        text = r.stdout.decode("utf-8", errors="replace")
                    else:
                        err = "pdftotext 退出码 %d: %s" % (
                            r.returncode, r.stderr.decode("utf-8", errors="replace")[:200])
                except Exception as ex:  # noqa: BLE001
                    err = "pdftotext 调用异常: %s" % ex
            else:
                err = "extract_error: 未检测到 pdftotext，无法抽取 PDF 文本"
        elif suffix == ".docx":
            text = extract_docx(path)
            if text is None:
                err = "extract_error: docx 抽取失败（标准库 zipfile 无法解析）"
        else:
            err = "extract_error: 不支持的文件类型 %s，已跳过" % (suffix or "(无后缀)")
        entry = {"file": name, "sha256": sha256_file(path)}
        if text is not None:
            entry["chars"] = len(text)
            corpus_parts.append("===== %s =====\n%s" % (name, text))
        if err:
            entry["extract_error"] = err
            errors.append("%s: %s" % (name, err))
        entries.append(entry)
    return entries, errors, "\n\n".join(corpus_parts)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="契约解析 + 文本抽取 + 答题纸生成 + 保底 partial result.json（第 1 步）")
    ap.add_argument("--input-dir", default="/input", help="输入目录（默认 /input）")
    ap.add_argument("--work-dir", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--output-dir", default="/app/output", help="输出目录（默认 /app/output）")
    args = ap.parse_args(argv)

    case_path = os.path.join(args.input_dir, "case.json")
    if not os.path.isfile(case_path):
        eprint("ERROR: 未找到 %s" % case_path)
        return 2
    try:
        case = json.loads(read_text(case_path))
    except json.JSONDecodeError as ex:
        eprint("ERROR: case.json 不是合法 JSON: %s" % ex)
        return 2
    if not isinstance(case, dict):
        eprint("ERROR: case.json 顶层必须是 JSON object")
        return 2

    case_id = case.get("case_id")
    if not case_id or not isinstance(case_id, str):
        eprint("ERROR: case.json 缺少字符串字段 case_id；"
               "result.json 必须含原 case_id，无法继续。请在 case.json 中补充 case_id。")
        return 2

    uncertainty = []
    fields, _ = parse_contract(case, uncertainty)

    os.makedirs(args.work_dir, exist_ok=True)
    entries, errors, corpus = extract_inputs(args.input_dir)
    uncertainty.extend(errors)
    if not corpus.strip():
        uncertainty.append("未能从 /input 抽取到任何正文文本，后续锚点复验将全部降级 pending_review")

    atomic_write(os.path.join(args.work_dir, "extracted_text.txt"), corpus)
    atomic_write_json(os.path.join(args.work_dir, "extracted_index.json"),
                      {"files": entries})

    # 答题纸：每个契约字段一格
    sheet = {
        "case_id": case_id,
        "generated_at": utcnow(),
        "contract_fields": {
            f: {"status": "empty", "value": None, "null_reason": None} for f in fields
        },
        "facet_coverage": {
            fac: {"status": "unable_to_check",
                  "notes": "（待 Agent 填写：checked_clean / issues_found / "
                           "partially_checked / unable_to_check）"} for fac in FACETS
        },
        "extraction": {"files": entries, "errors": errors},
        "uncertainty": uncertainty,
        "change_log": [{"ts": utcnow(), "event": "contract_init",
                        "detail": "契约字段 %d 个；抽取文件 %d 个；抽取错误 %d 个"
                                  % (len(fields), len(entries), len(errors))}],
    }
    atomic_write_json(os.path.join(args.work_dir, "answer_sheet.json"), sheet)

    # 保底 partial result.json（第一次调用就写）
    null_reasons = {}
    result = {}
    for f in fields:
        if f == "case_id":
            result[f] = case_id
        elif f == "status":
            result[f] = "partial"
        elif f == "findings":
            result[f] = []
        elif f == "review_report":
            result[f] = ""
        elif f == "sources":
            result[f] = {"input_files": entries}
        elif f == "uncertainty":
            result[f] = list(uncertainty) + ["保底 partial 输出：审查尚未执行，仅完成契约解析与文本抽取"]
        elif f == "change_log":
            result[f] = list(sheet["change_log"])
        else:
            result[f] = None
            null_reasons[f] = "契约字段语义未知，保底阶段无法填充，待 finalize 处理"
    if null_reasons:
        result["null_reasons"] = null_reasons
    atomic_write_json(os.path.join(args.output_dir, "result.json"), result)

    print("INIT_OK case_id=%s contract_fields=%d files_extracted=%d extract_errors=%d "
          "answer_sheet=%s result=%s"
          % (case_id, len(fields), len(entries), len(errors),
             os.path.join(args.work_dir, "answer_sheet.json"),
             os.path.join(args.output_dir, "result.json")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
