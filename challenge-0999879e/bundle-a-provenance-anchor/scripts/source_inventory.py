#!/usr/bin/env python3
"""source_inventory.py — 建立保真台账并立即产出保底 partial result.json。

职责：
1. 盘点输入目录全部文件：SHA-256、字节数、扩展名。
2. 按扩展名选择抽取方式：
   - .md / .txt / .tex 直读（utf-8, errors=replace）
   - .pdf 调用 pdftotext（shutil.which 检测；缺失则如实记录 extract_error）
   - .docx 记录 needs_office_tool（不造假、不静默跳过）
   - 其他扩展名记录 unsupported
3. 抽取文本写入 <work>/extracted/。
4. 产出 <work>/inventory.json（保真台账 + case_id + output_contract 字段集）。
5. 立即写出保底 partial result.json 到 --out 目录（契约字段允许 null + null_reasons）。

仅使用 Python 3 标准库。退出码：0 成功；非 0 失败并打印原因到 stderr。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

DEFAULT_CONTRACT = [
    "case_id", "status", "review_report", "findings",
    "sources", "uncertainty", "change_log",
]
TEXT_EXTS = {".md", ".txt", ".tex"}


def fail(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def normalize_contract(raw):
    """宽容处理 output_contract：list[str] 或 dict；否则回退默认字段集。"""
    if isinstance(raw, list) and raw and all(isinstance(x, str) for x in raw):
        return list(raw), None
    if isinstance(raw, dict) and raw and all(isinstance(k, str) for k in raw):
        return list(raw.keys()), "output_contract 为 dict 形式，取其键作为字段名"
    return list(DEFAULT_CONTRACT), (
        "case.json 中未找到可解析的 output_contract（既非字段名列表也非 dict），"
        "回退默认字段集 " + json.dumps(DEFAULT_CONTRACT, ensure_ascii=False)
    )


def extract_pdf(path):
    """返回 (text_or_None, status, note)。"""
    exe = shutil.which("pdftotext")
    if not exe:
        return None, "extract_error", "pdftotext 不可用（shutil.which 未找到），无法抽取 PDF 文本"
    try:
        proc = subprocess.run(
            [exe, "-enc", "UTF-8", path, "-"],
            capture_output=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return None, "extract_error", "pdftotext 超时（120s）"
    except OSError as e:
        return None, "extract_error", f"pdftotext 调用失败: {e}"
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()[:200]
        return None, "extract_error", f"pdftotext 退出码 {proc.returncode}: {err}"
    text = proc.stdout.decode("utf-8", errors="replace")
    if not text.strip():
        return None, "extract_error", "pdftotext 输出为空（可能为扫描件/图片型 PDF）"
    return text, "ok", None


def inventory_file(path, extracted_dir, index):
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    entry = {
        "file": name,
        "relpath": os.path.relpath(path),
        "ext": ext,
        "bytes": os.path.getsize(path),
        "sha256": sha256_of(path),
        "extract_method": None,
        "extract_status": None,
        "char_count": 0,
        "extracted_file": None,
        "note": None,
    }
    text = None
    if ext in TEXT_EXTS:
        entry["extract_method"] = "direct_read(utf-8,errors=replace)"
        try:
            text = read_text(path)
            entry["extract_status"] = "ok"
        except OSError as e:
            entry["extract_status"] = "extract_error"
            entry["note"] = f"直读失败: {e}"
    elif ext == ".pdf":
        entry["extract_method"] = "pdftotext"
        text, status, note = extract_pdf(path)
        entry["extract_status"] = status
        entry["note"] = note
    elif ext == ".docx":
        entry["extract_method"] = "none"
        entry["extract_status"] = "needs_office_tool"
        entry["note"] = "DOCX 需要 Office 工具链，本技能不猜测内容，待人工/外部工具抽取后复检"
    else:
        entry["extract_method"] = "none"
        entry["extract_status"] = "unsupported"
        entry["note"] = f"扩展名 {ext or '(无)'} 不在支持范围，未抽取"
    if text is not None:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        out_name = f"{index:02d}-{safe}.txt"
        out_path = os.path.join(extracted_dir, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        entry["char_count"] = len(text)
        entry["extracted_file"] = os.path.join("extracted", out_name)
    return entry


def main():
    ap = argparse.ArgumentParser(
        description="盘点输入文件、建立保真台账、立即写出保底 partial result.json")
    ap.add_argument("--input-dir", default="/input", help="输入目录（默认 /input）")
    ap.add_argument("--work-dir", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--out-dir", default="/app/output", help="输出目录（默认 /app/output）")
    args = ap.parse_args()

    input_dir = args.input_dir
    if not os.path.isdir(input_dir):
        fail(f"输入目录不存在: {input_dir}")
    os.makedirs(args.work_dir, exist_ok=True)
    os.makedirs(args.out_dir, exist_ok=True)
    extracted_dir = os.path.join(args.work_dir, "extracted")
    os.makedirs(extracted_dir, exist_ok=True)

    # ---- case.json：宽容解析 case_id 与 output_contract ----
    case_id, contract_fields, contract_note = "unknown-case", list(DEFAULT_CONTRACT), None
    case_path = os.path.join(input_dir, "case.json")
    if os.path.isfile(case_path):
        try:
            case = json.loads(read_text(case_path))
            if isinstance(case, dict):
                cid = case.get("case_id") or case.get("id")
                if isinstance(cid, str) and cid:
                    case_id = cid
                contract_fields, contract_note = normalize_contract(case.get("output_contract"))
            else:
                contract_note = "case.json 顶层不是对象，回退默认字段集"
        except (json.JSONDecodeError, OSError) as e:
            contract_note = f"case.json 解析失败（{e}），case_id 与契约字段均回退默认"
    else:
        contract_note = "未找到 case.json，case_id=unknown-case，契约字段回退默认"

    # ---- 盘点全部文件（按文件名排序，保证确定性）----
    files = []
    names = sorted(os.listdir(input_dir))
    idx = 0
    for name in names:
        p = os.path.join(input_dir, name)
        if not os.path.isfile(p):
            continue
        files.append(inventory_file(p, extracted_dir, idx))
        idx += 1
    if not files:
        fail(f"输入目录无任何文件: {input_dir}")

    inventory = {
        "case_id": case_id,
        "output_contract_fields": contract_fields,
        "contract_note": contract_note,
        "input_dir": os.path.abspath(input_dir),
        "file_count": len(files),
        "files": files,
    }
    inv_path = os.path.join(args.work_dir, "inventory.json")
    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2)

    # ---- 保底 partial result.json（第一次调用即产出）----
    result = {"case_id": case_id, "status": "partial"}
    null_reasons = {}
    for field in contract_fields:
        if field in ("case_id", "status"):
            continue
        result[field] = None
        null_reasons[field] = "审查尚未完成：source_inventory 仅建立保真台账，后续步骤将填充本字段"
    # 台账本身是已完成的真实工作，诚实填充 sources
    if "sources" in contract_fields:
        result["sources"] = [
            {"file": e["file"], "sha256": e["sha256"], "bytes": e["bytes"],
             "extract_status": e["extract_status"], "char_count": e["char_count"]}
            for e in files
        ]
        null_reasons.pop("sources", None)
    if "uncertainty" in contract_fields:
        unc = []
        if contract_note:
            unc.append(contract_note)
        for e in files:
            if e["extract_status"] != "ok":
                unc.append(f"{e['file']}: 抽取状态 {e['extract_status']}（{e['note']}）")
        result["uncertainty"] = unc
        null_reasons.pop("uncertainty", None)
    if "change_log" in contract_fields:
        result["change_log"] = [
            "source_inventory: 已建立保真台账（SHA-256/抽取方式/字符数/状态），写出保底 partial result.json"
        ]
        null_reasons.pop("change_log", None)
    if "findings" in contract_fields:
        result["findings"] = []
        null_reasons.pop("findings", None)
    result["null_reasons"] = null_reasons
    result["status_reason"] = "保底输出：仅完成输入盘点与文本抽取，审查与锚定复验尚未执行"

    tmp = os.path.join(args.out_dir, ".result.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(args.out_dir, "result.json"))

    ok = sum(1 for e in files if e["extract_status"] == "ok")
    print(json.dumps({
        "case_id": case_id,
        "contract_fields": contract_fields,
        "files": len(files),
        "extract_ok": ok,
        "extract_not_ok": len(files) - ok,
        "inventory": inv_path,
        "fallback_result": os.path.join(args.out_dir, "result.json"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
