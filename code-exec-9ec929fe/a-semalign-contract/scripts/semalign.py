#!/usr/bin/env python3
"""semalign.py — 上游契约与字段语义对齐工具（纯 Python 标准库，零第三方依赖）。

用途：在 /input 给定 case.json（含 case_id 与 output_contract）、task.md、
数据字典与数据文件（CSV 快照 / SQLite 数据库）的科研数据分析任务中，

  inspect  建立输入档案：逐文件 sha256/编码/行列/列类型/缺失/重复行，
           SQLite 表结构与 NULL 计数；解析 output_contract 生成机器可核
           对的 contract.json；把数据字典字段与实际列名做归一化相似度
           对齐，产出 field_mapping.json（含未对齐项，必须人工裁决）；
           并立即在输出目录写入 result.json 骨架（全部契约字段置 null、
           status=in_progress），保证任何时刻都有可交付的诚实半成品。
  gate     交付前契约门：case_id 一致性、契约字段齐全且非 null（除非
           status=partial 且该字段在 missing_fields 中给出原因）、声明
           的图表文件真实存在、provenance 完整。FAIL 以退出码 1 阻止
           交付，防止"看起来完成了"。

设计原则：本工具不做统计计算本身；它把"任务要求什么"与"数据实际有
什么"钉死在可机检的工件上，让 Agent 的每一步都有对齐依据。
"""
import argparse
import csv
import difflib
import hashlib
import json
import os
import platform
import re
import sqlite3
import sys

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "--", "missing"}
CSV_EXT = (".csv", ".tsv")
DB_EXT = (".db", ".sqlite", ".sqlite3")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_guess(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def norm_name(name):
    """列名归一化：小写、去单位括号、非字母数字折叠为下划线。"""
    s = str(name).strip().lower()
    s = re.sub(r"\([^)]*\)", " ", s)          # 去掉 (MPa) 这类单位注记
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"[^0-9a-z]+", "_", s).strip("_")
    return s


def guess_type(values):
    """values: 非缺失字符串列表。返回 int/float/str 与数值范围。"""
    if not values:
        return "empty", None, None
    ok_int = ok_float = True
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except ValueError:
            ok_float = False
            ok_int = False
            break
        if not re.fullmatch(r"[+-]?\d+", v.strip()):
            ok_int = False
    if ok_int:
        return "int", min(nums), max(nums)
    if ok_float:
        return "float", min(nums), max(nums)
    return "str", None, None


def profile_csv(path):
    text, enc = read_text_guess(path)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel_tab if path.endswith(".tsv") else csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    info = {"file": path, "kind": "csv", "sha256": sha256_file(path),
            "encoding": enc, "delimiter": dialect.delimiter}
    if not rows:
        info.update(n_rows=0, columns=[], warning="EMPTY_FILE")
        return info
    header = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    n_cols = len(header)
    ragged = sum(1 for r in body if len(r) != n_cols)
    seen = set()
    dups = 0
    for r in body:
        key = tuple(r)
        if key in seen:
            dups += 1
        seen.add(key)
    cols = []
    for j, name in enumerate(header):
        raw_vals = [(r[j].strip() if j < len(r) else "") for r in body]
        miss = sum(1 for v in raw_vals if v.lower() in MISSING_TOKENS)
        vals = [v for v in raw_vals if v.lower() not in MISSING_TOKENS]
        dtype, vmin, vmax = guess_type(vals)
        col = {"name": name, "normalized": norm_name(name), "dtype": dtype,
               "n_missing": miss, "n_nonmissing": len(vals)}
        if vmin is not None:
            col["min"], col["max"] = vmin, vmax
        else:
            col["n_distinct"] = len(set(vals))
        cols.append(col)
    info.update(n_rows=len(body), n_cols=n_cols, columns=cols,
                exact_duplicate_rows=dups, ragged_rows=ragged)
    return info


def profile_db(path):
    info = {"file": path, "kind": "sqlite", "sha256": sha256_file(path),
            "tables": []}
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tables:
            cols = con.execute("PRAGMA table_info(%s)" % _qident(t)).fetchall()
            n = con.execute("SELECT COUNT(*) FROM %s" % _qident(t)).fetchone()[0]
            tinfo = {"table": t, "n_rows": n, "columns": []}
            for cid, cname, ctype, notnull, dflt, pk in cols:
                nnull = con.execute(
                    "SELECT COUNT(*) FROM %s WHERE %s IS NULL"
                    % (_qident(t), _qident(cname))).fetchone()[0]
                tinfo["columns"].append({"name": cname, "declared_type": ctype,
                                         "n_null": nnull, "pk": bool(pk)})
            info["tables"].append(tinfo)
    finally:
        con.close()
    return info


def _qident(name):
    return '"' + str(name).replace('"', '""') + '"'


def find_inputs(input_dir):
    files = {"case_json": None, "task_md": None, "dictionaries": [],
             "csv": [], "db": [], "other": []}
    for root, _dirs, names in os.walk(input_dir):
        for n in sorted(names):
            p = os.path.join(root, n)
            ln = n.lower()
            if ln == "case.json":
                files["case_json"] = p
            elif ln == "task.md":
                files["task_md"] = p
            elif "dictionary" in ln or "dict" in ln or "schema" in ln:
                files["dictionaries"].append(p)
            elif ln.endswith(CSV_EXT):
                files["csv"].append(p)
            elif ln.endswith(DB_EXT):
                files["db"].append(p)
            else:
                files["other"].append(p)
    return files


def load_case(input_dir):
    p = os.path.join(input_dir, "case.json")
    if not os.path.isfile(p):
        return None, "NO_CASE_JSON: /input/case.json 不存在，无法建立契约"
    try:
        return json.load(open(p, encoding="utf-8")), None
    except Exception as e:  # noqa: BLE001
        return None, "CASE_JSON_UNPARSEABLE: %s" % e


def contract_fields(case):
    """从 case.json 提取 output_contract 字段名列表，兼容 dict/list/str。"""
    oc = (case or {}).get("output_contract")
    if oc is None:
        return [], "output_contract 缺失：以 case_id/status/anomalies/provenance 为最低契约"
    if isinstance(oc, dict):
        for key in ("fields", "required", "outputs"):
            if key in oc:
                oc = oc[key]
                break
        else:
            return sorted(oc.keys()), None
    if isinstance(oc, str):
        return [oc], None
    if isinstance(oc, list):
        out = []
        for item in oc:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.append(item.get("name") or item.get("field") or json.dumps(item, ensure_ascii=False))
        return out, None
    return [], "output_contract 形态无法识别: %s" % type(oc).__name__


def dict_field_names(dict_paths):
    """从数据字典文件提取字段名候选（json: 键或 name 列；csv: 首列）。"""
    names = []
    for p in dict_paths:
        try:
            if p.lower().endswith(".json"):
                d = json.load(open(p, encoding="utf-8"))
                if isinstance(d, dict):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            names.append(str(v.get("name") or k))
                        else:
                            names.append(str(k))
                elif isinstance(d, list):
                    for item in d:
                        if isinstance(item, dict):
                            names.append(str(item.get("name") or item.get("column") or item))
                        else:
                            names.append(str(item))
            else:
                text, _enc = read_text_guess(p)
                for row in csv.reader(text.splitlines()):
                    if row:
                        names.append(row[0].strip())
        except Exception as e:  # noqa: BLE001
            names.append("UNREADABLE_DICT:%s:%s" % (os.path.basename(p), e))
    return [n for n in names if n]


def align_fields(dict_names, actual_cols):
    """归一化相似度对齐；返回映射与两侧未对齐清单。"""
    mapping, used = [], set()
    norm_actual = {}
    for c in actual_cols:
        norm_actual.setdefault(norm_name(c), []).append(c)
    for dn in dict_names:
        nd = norm_name(dn)
        if nd in norm_actual:
            mapping.append({"dictionary_field": dn, "column": norm_actual[nd][0],
                            "score": 1.0, "method": "exact_normalized"})
            used.add(norm_actual[nd][0])
            continue
        best, best_score = None, 0.0
        for na, originals in norm_actual.items():
            s = difflib.SequenceMatcher(None, nd, na).ratio()
            if len(nd) >= 4 and len(na) >= 4 and (nd.startswith(na) or na.startswith(nd)):
                s = max(s, 0.9)  # 缩写前缀对齐，如 temperature ↔ temp
            if s > best_score:
                best, best_score = originals[0], s
        if best is not None and best_score >= 0.6:
            mapping.append({"dictionary_field": dn, "column": best,
                            "score": round(best_score, 3), "method": "fuzzy",
                            "needs_human_confirm": best_score < 0.85})
            used.add(best)
        else:
            mapping.append({"dictionary_field": dn, "column": None,
                            "score": round(best_score, 3), "method": "UNMAPPED",
                            "needs_human_confirm": True})
    unmapped_cols = [c for c in actual_cols if c not in used]
    return mapping, unmapped_cols


def cmd_inspect(args):
    input_dir, work, output = args.input, args.work, args.output
    os.makedirs(work, exist_ok=True)
    os.makedirs(output, exist_ok=True)
    case, case_err = load_case(input_dir)
    case_id = (case or {}).get("case_id") or (case or {}).get("id") or "UNKNOWN_CASE_ID"
    fields, fields_warn = contract_fields(case)
    found = find_inputs(input_dir)

    profiles = []
    for p in found["csv"]:
        try:
            profiles.append(profile_csv(p))
        except Exception as e:  # noqa: BLE001
            profiles.append({"file": p, "kind": "csv", "error": "PROFILE_FAILED: %s" % e})
    for p in found["db"]:
        try:
            profiles.append(profile_db(p))
        except Exception as e:  # noqa: BLE001
            profiles.append({"file": p, "kind": "sqlite", "error": "PROFILE_FAILED: %s" % e})

    actual_cols = []
    for prof in profiles:
        if prof.get("kind") == "csv" and "columns" in prof:
            actual_cols.extend(c["name"] for c in prof["columns"])
        elif prof.get("kind") == "sqlite":
            for t in prof.get("tables", []):
                actual_cols.extend(c["name"] for c in t["columns"])
    dnames = dict_field_names(found["dictionaries"])
    mapping, unmapped_cols = align_fields(dnames, actual_cols)

    warnings = [w for w in (case_err, fields_warn) if w]
    contract = {
        "case_id": case_id,
        "output_contract_fields": fields,
        "input_files": {k: v for k, v in found.items() if v},
        "warnings": warnings,
        "obligations": [
            "result.json 必须含 case_id 且等于 %s" % case_id,
            "每个 output_contract 字段必须出现且非 null（partial 时须在 missing_fields 说明原因）",
            "图表字段中的文件路径必须真实存在",
            "anomalies 必须列出缺失/异常/未裁决项，不得静默",
        ],
    }
    _dump(os.path.join(work, "contract.json"), contract)
    _dump(os.path.join(work, "profile.json"), {"case_id": case_id, "inputs": profiles})
    _dump(os.path.join(work, "field_mapping.json"),
          {"mapping": mapping, "unmapped_actual_columns": unmapped_cols,
           "note": "needs_human_confirm=true 的映射必须人工核对数据字典原文后再使用"})
    with open(os.path.join(work, "profile.md"), "w", encoding="utf-8") as f:
        f.write(render_profile_md(case_id, profiles, mapping, unmapped_cols, warnings))

    skeleton = {
        "case_id": case_id,
        "status": "in_progress",
        **{k: None for k in fields},
        "anomalies": warnings,
        "missing_fields": [],
        "provenance": {
            "input_hashes": {os.path.basename(p["file"]): p.get("sha256")
                             for p in profiles if p.get("sha256")},
            "python": platform.python_version(),
            "tool": "semalign.py inspect",
            "note": "骨架由 semalign inspect 生成；每个契约字段必须用真实计算结果填充，禁止凭标签臆造",
        },
    }
    _dump(os.path.join(output, "result.json"), skeleton)
    print("INSPECT OK case_id=%s contract_fields=%d mapped=%d unmapped_dict=%d unmapped_cols=%d"
          % (case_id, len(fields),
             sum(1 for m in mapping if m.get("column")),
             sum(1 for m in mapping if not m.get("column")), len(unmapped_cols)))
    for w in warnings:
        print("WARNING:", w)
    return 0


def render_profile_md(case_id, profiles, mapping, unmapped_cols, warnings):
    L = ["# 输入档案（semalign inspect）", "", "case_id: `%s`" % case_id, ""]
    for w in warnings:
        L.append("- ⚠ " + w)
    for p in profiles:
        L.append("\n## %s" % p["file"])
        if "error" in p:
            L.append("- " + p["error"])
            continue
        L.append("- sha256: `%s`" % p["sha256"])
        if p["kind"] == "csv":
            L.append("- 编码 %s，分隔符 %r，数据行 %d，列 %d，完全重复行 %d，列数不齐行 %d"
                     % (p["encoding"], p["delimiter"], p["n_rows"], p["n_cols"],
                        p["exact_duplicate_rows"], p["ragged_rows"]))
            for c in p["columns"]:
                extra = ("范围 [%s, %s]" % (c["min"], c["max"])) if "min" in c \
                    else "distinct=%d" % c.get("n_distinct", 0)
                L.append("  - `%s` (%s)：缺失 %d/%d，%s"
                         % (c["name"], c["dtype"], c["n_missing"],
                            c["n_missing"] + c["n_nonmissing"], extra))
        else:
            for t in p["tables"]:
                L.append("- 表 `%s`：%d 行" % (t["table"], t["n_rows"]))
                for c in t["columns"]:
                    L.append("  - `%s` %s NULL=%d%s" % (c["name"], c["declared_type"],
                                                        c["n_null"], " PK" if c["pk"] else ""))
    L.append("\n## 字段对齐（数据字典 → 实际列）")
    for m in mapping:
        flag = " ⚠需人工确认" if m.get("needs_human_confirm") else ""
        L.append("- `%s` → `%s` (score=%s, %s)%s"
                 % (m["dictionary_field"], m.get("column"), m.get("score"), m["method"], flag))
    if unmapped_cols:
        L.append("- 未被字典覆盖的实际列: %s" % ", ".join("`%s`" % c for c in unmapped_cols))
    return "\n".join(L) + "\n"


def cmd_gate(args):
    case, case_err = load_case(args.input)
    fields, _ = contract_fields(case)
    rpath = os.path.join(args.output, "result.json")
    problems = []
    if case_err:
        problems.append(case_err)
    if not os.path.isfile(rpath):
        print("GATE FAIL: %s 不存在" % rpath)
        return 1
    try:
        result = json.load(open(rpath, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print("GATE FAIL: result.json 无法解析: %s" % e)
        return 1
    case_id = (case or {}).get("case_id") or (case or {}).get("id")
    if case_id and result.get("case_id") != case_id:
        problems.append("case_id 不一致: result=%r case=%r" % (result.get("case_id"), case_id))
    status = result.get("status")
    if status not in ("success", "partial", "failed"):
        problems.append("status 必须是 success|partial|failed，当前 %r" % status)
    missing_declared = {m.get("field") for m in result.get("missing_fields", [])
                        if isinstance(m, dict)}
    for k in fields:
        if k not in result:
            problems.append("契约字段缺失: %s" % k)
        elif result[k] is None:
            if status == "partial" and k in missing_declared:
                continue
            problems.append("契约字段为 null 且未在 missing_fields 说明: %s" % k)
    if status == "success" and result.get("missing_fields"):
        problems.append("status=success 但 missing_fields 非空")
    if not isinstance(result.get("anomalies"), list):
        problems.append("anomalies 必须是数组")
    figs = result.get("figures") or result.get("figure_files") or []
    if isinstance(figs, str):
        figs = [figs]
    for fp in figs:
        if not isinstance(fp, str):
            continue
        p = fp if os.path.isabs(fp) else os.path.join(args.output, fp)
        if not os.path.isfile(p):
            problems.append("声明的图文件不存在: %s" % fp)
    prov = result.get("provenance") or {}
    if not prov.get("input_hashes"):
        problems.append("provenance.input_hashes 缺失：复核者无法确认输入版本")
    if problems:
        print("GATE FAIL (%d 项):" % len(problems))
        for p in problems:
            print(" -", p)
        return 1
    print("GATE PASS: case_id=%s status=%s 契约字段 %d 个全部落实"
          % (result.get("case_id"), status, len(fields)))
    return 0


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("inspect", help="建立输入档案、契约与 result.json 骨架")
    pi.add_argument("--input", required=True)
    pi.add_argument("--work", required=True)
    pi.add_argument("--output", required=True)
    pi.set_defaults(fn=cmd_inspect)
    pg = sub.add_parser("gate", help="交付前契约门")
    pg.add_argument("--input", required=True)
    pg.add_argument("--output", required=True)
    pg.set_defaults(fn=cmd_gate)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
