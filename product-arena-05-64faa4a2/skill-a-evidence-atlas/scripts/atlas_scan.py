#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""atlas_scan.py — 材料清点与参数台账构建（evidence-atlas）

扫描给定输入目录：
  1. 枚举全部文件，记录 relpath、大小、sha256、类型猜测；
  2. 对 yaml/json/ini/toml(简)/log/txt/md/csv 等文本材料提取候选参数：
     - 键值对（key: value / key=value，含行内形式）
     - 命令行 flag（--lr 0.001 / --batch-size=32）
     - 版本号模式（v1.2.3、torch 2.1、python=3.10 等）
     - seed、路径、URL
  3. 每个候选参数记录 name/value/unit(启发)/kind/source(file:line)/evidence(原文行)；
  4. 对二进制与不可解析文件诚实记录为未解析；
  5. 检测同名参数跨文件取值冲突。

输出：atlas.json（机器读台账）、atlas.md（人读摘要）。

仅使用 Python 标准库。若环境存在 PyYAML 则用于 YAML 解析并在元数据中注明；
否则降级为行解析并注明降级。输出确定性：无时间戳，全量排序，同输入同输出。

用法：
  python3 atlas_scan.py /input --out /app/work/atlas
  python3 atlas_scan.py --input /input --out /app/work/atlas
"""

import argparse
import hashlib
import json
import os
import re
import sys

TOOL_NAME = "atlas_scan"
TOOL_VERSION = "1.0.0"

# 可尝试按文本解析的扩展名（其余一律记为未解析/二进制）
TEXT_EXTS = {
    ".yaml", ".yml", ".json", ".ini", ".cfg", ".conf", ".toml",
    ".log", ".txt", ".md", ".markdown", ".csv", ".tsv",
    ".py", ".sh", ".bash", ".env", ".properties",
}

TYPE_BY_EXT = {
    ".yaml": "yaml", ".yml": "yaml", ".json": "json",
    ".ini": "ini", ".cfg": "ini", ".conf": "ini",
    ".toml": "toml", ".log": "log", ".txt": "text",
    ".md": "markdown", ".markdown": "markdown",
    ".csv": "csv", ".tsv": "csv",
    ".py": "code-python", ".sh": "code-shell", ".bash": "code-shell",
    ".env": "env", ".properties": "ini",
    ".pdf": "pdf", ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".zip": "archive", ".gz": "archive", ".pt": "binary-model",
    ".pth": "binary-model", ".ckpt": "binary-model", ".bin": "binary",
}

MAX_READ_BYTES = 8 * 1024 * 1024  # 单文件超过 8MB 只读前 8MB，并注明截断

# ---- 提取用正则 ----
# 行内 key=value（不要求行首，兼容日志中的 seed=42 等）
KV_EQ_RE = re.compile(r'(?<![\w./-])([A-Za-z_][\w.\-]{0,60})\s*=\s*([^\s,;#"\']{1,120})')
# 行首 key: value（yaml/ini/md 风格；要求键后紧跟冒号与空白，避免误吃 "注意：xxx" 之外的行）
KV_COLON_RE = re.compile(
    r'^\s{0,12}["\']?([A-Za-z_][\w.\-]{0,60})["\']?\s*:\s+(\S[^\n#]{0,160}?)\s*(?:#.*)?$')
# 命令行 flag：--lr 0.001 / --batch-size=32 / -e 10
FLAG_RE = re.compile(r'(?<![\w/])--?([A-Za-z][\w\-]{0,40})[=\s]+([^\s,;]{1,80})')
# 已知软件名 + 版本号（python 3.10 / torch=2.1.0 / cuda-12.1）
VERSION_KNOWN_RE = re.compile(
    r'\b(python|pytorch|torch|tensorflow|tf|cuda|cudnn|numpy|pandas|scipy|'
    r'scikit-learn|sklearn|transformers|deepspeed|mmcv|apex|xgboost|lightgbm)'
    r'[\s=\-/]{0,3}(v?\d+\.\d+(?:\.\d+){0,2})', re.IGNORECASE)
# 独立 v 前缀版本号：v1.2.3
VERSION_V_RE = re.compile(r'(?<![\w.])(v\d+\.\d+(?:\.\d+){0,2})\b')
URL_RE = re.compile(r'https?://[^\s)\]>"\']{3,200}')
# 绝对路径（先抽取 URL 并掩蔽，避免把 URL 的路径部分重复计入）
PATH_RE = re.compile(r'(?<![\w:])/(?:[\w.\-]{1,64}/){1,8}[\w.\-]{0,64}')

KNOWN_UNITS = {
    "%", "ms", "s", "sec", "min", "h", "hr", "hrs",
    "B", "KB", "MB", "GB", "TB", "KiB", "MiB", "GiB",
    "kHz", "MHz", "GHz", "Hz", "W", "V", "G", "M",
}
UNIT_RE = re.compile(r'^(-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?)([a-zA-Z%µ]+)$')

BOOL_WORDS = {"true", "false", "yes", "no", "on", "off", "none", "null"}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def guess_type(relpath):
    ext = os.path.splitext(relpath)[1].lower()
    return TYPE_BY_EXT.get(ext, "unknown" + (ext if ext else ""))


def split_unit(value):
    """单位启发：数值后紧跟已知单位则拆出；否则 unit 为空。"""
    m = UNIT_RE.match(value)
    if m and m.group(2) in KNOWN_UNITS:
        return m.group(1), m.group(2)
    return value, ""


def clean_value(v):
    v = v.strip().strip('"').strip("'").rstrip(",")
    return v[:160]


def norm_name(name):
    return name.strip().lower().replace("-", "_")


def flatten(obj, prefix=""):
    """把嵌套 dict/list 打平为 dotted 路径键。键排序保证确定性。"""
    if isinstance(obj, dict):
        for k in sorted(obj.keys(), key=str):
            yield from flatten(obj[k], "%s%s." % (prefix, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flatten(v, "%s%d." % (prefix, i))
    else:
        yield prefix.rstrip("."), obj


def scalar_to_str(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def find_line(lines, key, value_str):
    """在原文中为结构化解析出的键定位行号：找同时含末段键名与值串的行；找不到返回 0。"""
    last = key.split(".")[-1]
    pat_kv = re.compile(r'["\']?%s["\']?\s*[:=]' % re.escape(last))
    fallback = 0
    for i, line in enumerate(lines, 1):
        if pat_kv.search(line):
            if value_str and value_str in line:
                return i
            if fallback == 0:
                fallback = i
    return fallback


def extract_structured(relpath, ftype, text, lines, notes):
    """对 yaml/json 做结构化解析。返回候选列表；解析失败返回 None（调用方降级）。"""
    cands = []
    if ftype == "json":
        try:
            data = json.loads(text)
        except Exception as e:
            notes.append("%s: JSON 解析失败（%s），降级为行解析" % (relpath, e))
            return None
        for key, val in flatten(data):
            vs = clean_value(scalar_to_str(val))
            if not vs:
                continue
            ln = find_line(lines, key, vs)
            num, unit = split_unit(vs)
            cands.append({
                "name": key, "value": num, "unit": unit, "kind": "parameter",
                "line": ln, "col": 0,
                "evidence": lines[ln - 1].strip()[:240] if 0 < ln <= len(lines) else "",
            })
        return cands

    if ftype == "yaml":
        try:
            import yaml  # type: ignore
        except Exception:
            notes.append(
                "%s: 环境无 PyYAML，YAML 降级为行解析（嵌套结构可能丢失，"
                "仅提取行首 key: value）" % relpath)
            return None
        try:
            data = yaml.safe_load(text)
        except Exception as e:
            notes.append("%s: PyYAML 解析失败（%s），降级为行解析" % (relpath, e))
            return None
        if not isinstance(data, (dict, list)):
            return []  # 空文档或纯标量：无参数可提，仍视为已解析
        notes.append("%s: 使用 PyYAML 结构化解析" % relpath)
        for key, val in flatten(data):
            vs = clean_value(scalar_to_str(val))
            if not vs or vs.lower() in BOOL_WORDS and not isinstance(val, bool):
                continue
            ln = find_line(lines, key, vs)
            num, unit = split_unit(vs)
            cands.append({
                "name": key, "value": num, "unit": unit, "kind": "parameter",
                "line": ln, "col": 0,
                "evidence": lines[ln - 1].strip()[:240] if 0 < ln <= len(lines) else "",
            })
        return cands

    return None  # 其他类型不使用结构化解析


def extract_generic(relpath, lines):
    """行级通用提取：键值对、flag、版本号、URL、绝对路径。"""
    cands = []
    for ln, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        evidence = line.strip()[:240]
        if not evidence:
            continue
        # URL 先行，掩蔽后供路径正则使用
        url_spans = []
        for m in URL_RE.finditer(line):
            url_spans.append(m.span())
            cands.append({"name": "url", "value": m.group(0), "unit": "",
                          "kind": "url", "line": ln, "col": m.start(),
                          "evidence": evidence})
        masked = list(line)
        for s, e in url_spans:
            for i in range(s, e):
                masked[i] = " "
        masked = "".join(masked)

        for m in PATH_RE.finditer(masked):
            cands.append({"name": "path", "value": m.group(0), "unit": "",
                          "kind": "path", "line": ln, "col": m.start(),
                          "evidence": evidence})

        seen_eq_cols = set()
        for m in KV_EQ_RE.finditer(masked):
            name, value = m.group(1), clean_value(m.group(2))
            if not value or value.lower() in BOOL_WORDS:
                continue
            seen_eq_cols.add(m.start())
            num, unit = split_unit(value)
            cands.append({"name": name, "value": num, "unit": unit,
                          "kind": "parameter", "line": ln, "col": m.start(),
                          "evidence": evidence})

        # 行首 key: value（yaml/ini/md 风格）。键中含空格或值中含 ": " 的散文行
        # 由正则结构本身限制（键仅允许 [\w.\-]，值需非空）。
        m = KV_COLON_RE.match(masked)
        if m:
            name, value = m.group(1), clean_value(m.group(2))
            if value and value.lower() not in BOOL_WORDS:
                num, unit = split_unit(value)
                cands.append({"name": name, "value": num, "unit": unit,
                              "kind": "parameter", "line": ln, "col": m.start(1),
                              "evidence": evidence})

        for m in FLAG_RE.finditer(masked):
            name, value = m.group(1), clean_value(m.group(2))
            if not value or value.startswith("-") or value.lower() in BOOL_WORDS:
                continue
            num, unit = split_unit(value)
            cands.append({"name": "flag:" + name, "value": num, "unit": unit,
                          "kind": "flag", "line": ln, "col": m.start(),
                          "evidence": evidence})

        for m in VERSION_KNOWN_RE.finditer(masked):
            cands.append({"name": m.group(1).lower(), "value": m.group(2),
                          "unit": "", "kind": "version", "line": ln,
                          "col": m.start(), "evidence": evidence})
        for m in VERSION_V_RE.finditer(masked):
            cands.append({"name": "version", "value": m.group(1),
                          "unit": "", "kind": "version", "line": ln,
                          "col": m.start(), "evidence": evidence})
    return cands


def detect_conflicts(params):
    """同名（规范化后）参数取值不一致 → 冲突清单。"""
    groups = {}
    for p in params:
        if p["kind"] not in ("parameter", "flag"):
            continue
        key = norm_name(p["name"])
        groups.setdefault(key, []).append(p)
    conflicts = []
    for name in sorted(groups):
        vals = {}
        for p in groups[name]:
            vals.setdefault(p["value"], []).append(
                {"file": p["source"]["file"], "line": p["source"]["line"]})
        if len(vals) > 1:
            conflicts.append({
                "name": name,
                "occurrences": [
                    {"value": v, "locations": locs}
                    for v, locs in sorted(vals.items())
                ],
            })
    return conflicts


def scan(input_dir):
    input_dir = os.path.abspath(input_dir)
    files = []
    unparsed = []
    notes = []
    raw_params = []

    relpaths = []
    for dirpath, dirnames, filenames in os.walk(input_dir):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            relpaths.append(os.path.relpath(full, input_dir))
    relpaths.sort()

    for rel in relpaths:
        full = os.path.join(input_dir, rel)
        size = os.path.getsize(full)
        digest = sha256_of(full)
        ftype = guess_type(rel)
        entry = {"path": rel, "relpath": rel, "size_bytes": size,
                 "sha256": digest, "type": ftype,
                 "status": "pending", "note": ""}
        ext = os.path.splitext(rel)[1].lower()
        if ext not in TEXT_EXTS:
            entry["status"] = "unparsed"
            entry["note"] = "二进制或不支持的类型，未解析；如需其中信息请人工读取或用专门工具"
            files.append(entry)
            unparsed.append({"file": rel, "reason": entry["note"]})
            continue
        try:
            with open(full, "rb") as f:
                blob = f.read(MAX_READ_BYTES + 1)
        except OSError as e:
            entry["status"] = "unparsed"
            entry["note"] = "读取失败：%s" % e
            files.append(entry)
            unparsed.append({"file": rel, "reason": entry["note"]})
            continue
        truncated = len(blob) > MAX_READ_BYTES
        blob = blob[:MAX_READ_BYTES]
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            entry["status"] = "unparsed"
            entry["note"] = "非 UTF-8 文本（疑似二进制），未解析"
            files.append(entry)
            unparsed.append({"file": rel, "reason": entry["note"]})
            continue
        if truncated:
            entry["note"] = "文件超过 8MB，仅解析前 8MB（截断）"
        lines = text.splitlines()
        entry["status"] = "parsed"
        entry["lines"] = len(lines)
        files.append(entry)

        cands = extract_structured(rel, ftype, text, lines, notes)
        if cands is None:
            cands = extract_generic(rel, lines)
        for c in cands:
            c["file"] = rel
        raw_params.extend(cands)

    # 去重 + 排序 + 赋 ID（确定性）
    seen = set()
    uniq = []
    for c in raw_params:
        key = (c["file"], c["line"], c["col"], c["kind"], c["name"], c["value"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    uniq.sort(key=lambda c: (c["file"], c["line"], c["col"], c["kind"], c["name"]))

    params = []
    for i, c in enumerate(uniq, 1):
        params.append({
            "id": "P%03d" % i,
            "name": c["name"],
            "value": c["value"],
            "unit": c["unit"],
            "kind": c["kind"],
            "source": {"file": c["file"], "line": c["line"]},
            "evidence": c["evidence"],
        })

    conflicts = detect_conflicts(params)

    atlas = {
        "meta": {
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "input_dir": input_dir,
            "file_count": len(files),
            "parsed_count": sum(1 for f in files if f["status"] == "parsed"),
            "unparsed_count": sum(1 for f in files if f["status"] == "unparsed"),
            "parameter_count": len(params),
            "conflict_count": len(conflicts),
            "notes": notes,
        },
        "files": files,
        "parameters": params,
        "conflicts": conflicts,
        "unparsed": unparsed,
    }
    return atlas


def render_md(atlas):
    out = []
    meta = atlas["meta"]
    out.append("# 材料清单与参数台账摘要（atlas.md）")
    out.append("")
    out.append("- 输入目录：`%s`" % meta["input_dir"])
    out.append("- 文件总数：%d（已解析 %d / 未解析 %d）" % (
        meta["file_count"], meta["parsed_count"], meta["unparsed_count"]))
    out.append("- 候选参数：%d；取值冲突：%d" % (
        meta["parameter_count"], meta["conflict_count"]))
    if meta["notes"]:
        out.append("- 解析备注：")
        for n in meta["notes"]:
            out.append("  - %s" % n)
    out.append("")
    out.append("## 文件清单")
    out.append("")
    out.append("| 文件 | 大小(B) | sha256(前12) | 类型 | 状态 | 备注 |")
    out.append("| --- | ---: | --- | --- | --- | --- |")
    for f in atlas["files"]:
        out.append("| `%s` | %d | `%s` | %s | %s | %s |" % (
            f["relpath"], f["size_bytes"], f["sha256"][:12],
            f["type"], f["status"], f.get("note", "")))
    out.append("")
    out.append("## 参数候选表")
    out.append("")
    out.append("| ID | 名称 | 取值 | 单位 | 类别 | 来源(file:line) | 原文 |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for p in atlas["parameters"]:
        ev = p["evidence"].replace("|", "\\|")
        if len(ev) > 90:
            ev = ev[:87] + "..."
        out.append("| %s | `%s` | `%s` | %s | %s | `%s:%d` | %s |" % (
            p["id"], p["name"], p["value"], p["unit"] or "—", p["kind"],
            p["source"]["file"], p["source"]["line"], ev))
    out.append("")
    out.append("## 取值冲突（同名参数多处取值不一致，须人工裁决后方可写入正文）")
    out.append("")
    if not atlas["conflicts"]:
        out.append("（无）")
    for c in atlas["conflicts"]:
        out.append("- `%s`：" % c["name"])
        for occ in c["occurrences"]:
            locs = "、".join("`%s:%d`" % (l["file"], l["line"])
                             for l in occ["locations"])
            out.append("  - 取值 `%s` ← %s" % (occ["value"], locs))
    out.append("")
    out.append("## 未解析 / 跳过清单")
    out.append("")
    if not atlas["unparsed"]:
        out.append("（无）")
    for u in atlas["unparsed"]:
        out.append("- `%s`：%s" % (u["file"], u["reason"]))
    out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="材料清点与参数台账构建（evidence-atlas）")
    ap.add_argument("input_pos", nargs="?", default=None, help="输入目录（位置参数）")
    ap.add_argument("--input", dest="input_opt", default=None, help="输入目录")
    ap.add_argument("--out", required=True, help="输出目录（写 atlas.json 与 atlas.md）")
    args = ap.parse_args(argv)
    input_dir = args.input_opt or args.input_pos
    if not input_dir:
        ap.error("必须指定输入目录（位置参数或 --input）")
    if not os.path.isdir(input_dir):
        print("错误：输入目录不存在：%s" % input_dir, file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)
    atlas = scan(input_dir)
    jpath = os.path.join(args.out, "atlas.json")
    mpath = os.path.join(args.out, "atlas.md")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(atlas, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(render_md(atlas))
    meta = atlas["meta"]
    print("atlas_scan 完成：文件 %d（解析 %d / 未解析 %d），参数 %d，冲突 %d" % (
        meta["file_count"], meta["parsed_count"], meta["unparsed_count"],
        meta["parameter_count"], meta["conflict_count"]))
    print("输出：%s" % jpath)
    print("输出：%s" % mpath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
