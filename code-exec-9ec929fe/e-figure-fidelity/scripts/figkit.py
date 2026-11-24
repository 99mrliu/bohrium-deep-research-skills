#!/usr/bin/env python3
"""figkit.py — 图表保真与渲染证据链（核心逻辑纯标准库；matplotlib 仅为
可选渲染后端）。

重心是下游渲染工程：图表类静默错误（轴标签/单位/图例与原始数据不一致、
被排除的缺失点无人知晓、图与数据对不上、渲染库缺失时交付一张旧图）靠
机制拦截，不靠自觉：

  render  渲染 hist/scatter/bar/line。每张图强制配套：
          <out>.data.csv（绘入图的全部数据点）与 <out>.receipt.json
          （源文件 sha256、列名、绘入/排除点数、轴标签与单位原文、
          值域）。无 matplotlib（或 FIGKIT_NO_MPL=1）时写
          SKIPPED_no_matplotlib 回执 + 数据 CSV，诚实降级。
  lint    交付前机检：receipt 中的列名必须真实存在于源表；轴标签
          中的单位必须能在数据字典中找到（字典字段 unit 或列名括号
          注记）；receipt 值域与源表实测值域一致；PNG 文件真实存在
          且非空；每个 receipt 必须有对应 PNG 或 SKIPPED 状态。
          任何违例以退出码 1 阻断交付。
  check   对照 result.json：figures 字段列出的每个文件都存在、且
          （若是 PNG）配有 receipt；防止"图字段登记了路径但文件没
          生成"。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--"}
UNIT_RE = re.compile(r"[\(\[]\s*([A-Za-z0-9μ°/%^*\.]+(?:\s*/\s*[A-Za-z0-9μ°/%^*\.]+)?)\s*[\)\]]")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_table(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    if not rows:
        raise SystemExit("EMPTY_TABLE: %s" % path)
    return [h.strip() for h in rows[0]], [r for r in rows[1:] if any(c.strip() for c in r)]


def col_idx(header, name):
    if name not in header:
        raise SystemExit("MISSING_COLUMN %r；可用: %s" % (name, ", ".join(header)))
    return header.index(name)


def to_float(v):
    s = str(v).strip()
    if s.lower() in MISSING:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def collect_points(header, body, args):
    """返回 (points, n_excluded, receipt_fields)。points 依图型而异。"""
    jx = col_idx(header, args.x)
    n_excl = 0
    if args.kind == "hist":
        xs = []
        for r in body:
            v = to_float(r[jx] if jx < len(r) else "")
            if v is None:
                n_excl += 1
            else:
                xs.append(v)
        return xs, n_excl, {"x_column": args.x,
                            "x_range": [min(xs), max(xs)] if xs else None}
    if args.kind in ("scatter", "line"):
        jy = col_idx(header, args.y)
        pts = []
        for r in body:
            a = to_float(r[jx] if jx < len(r) else "")
            b = to_float(r[jy] if jy < len(r) else "")
            if a is None or b is None:
                n_excl += 1
                continue
            pts.append((a, b))
        return pts, n_excl, {"x_column": args.x, "y_column": args.y,
                             "x_range": [min(p[0] for p in pts)] and
                                        [min(p[0] for p in pts), max(p[0] for p in pts)] if pts else None,
                             "y_range": [min(p[1] for p in pts), max(p[1] for p in pts)] if pts else None}
    if args.kind == "bar":
        counts = {}
        for r in body:
            s = (r[jx] if jx < len(r) else "").strip()
            if s.lower() in MISSING:
                n_excl += 1
                continue
            counts[s] = counts.get(s, 0) + 1
        return counts, n_excl, {"x_column": args.x, "categories": counts}
    raise SystemExit("FIGURE_KIND_UNKNOWN: %s" % args.kind)


def write_data_csv(path, kind, points, xname, yname):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if kind == "hist":
            w.writerow([xname])
            for v in points:
                w.writerow([v])
        elif kind in ("scatter", "line"):
            w.writerow([xname, yname])
            for a, b in points:
                w.writerow([a, b])
        else:
            w.writerow([xname, "count"])
            for k, v in points.items():
                w.writerow([k, v])


def cmd_render(args):
    header, body = read_table(args.table)
    points, n_excl, extra = collect_points(header, body, args)
    receipt = {"tool": "figkit render", "kind": args.kind, "table": args.table,
               "table_sha256": sha256_file(args.table),
               "n_rows_source": len(body), "n_plotted": (
                   len(points) if not isinstance(points, dict)
                   else sum(points.values())),
               "n_excluded_missing": n_excl,
               "title": args.title, "xlabel": args.xlabel, "ylabel": args.ylabel,
               "out": args.out}
    receipt.update(extra)
    data_csv = args.out + ".data.csv"
    write_data_csv(data_csv, args.kind, points, args.x, getattr(args, "y", None))
    try:
        if os.environ.get("FIGKIT_NO_MPL"):
            raise ImportError("forced by FIGKIT_NO_MPL")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        receipt.update(status="SKIPPED_no_matplotlib", data_csv=data_csv,
                       note="渲染库不可用，图未生成；绘图数据已保存可复绘。"
                            " result.json 必须如实报告，不得交付不存在或内容不符的图。")
        _dump(args.out + ".receipt.json", receipt)
        print("FIGURE SKIPPED_no_matplotlib: %s（数据 %s）" % (args.out, data_csv))
        return 0
    plt.figure()
    if args.kind == "hist":
        plt.hist(points, bins=args.bins)
    elif args.kind == "scatter":
        plt.scatter([p[0] for p in points], [p[1] for p in points], s=8)
    elif args.kind == "line":
        order = sorted(range(len(points)), key=lambda i: points[i][0])
        plt.plot([points[i][0] for i in order], [points[i][1] for i in order])
    else:
        plt.bar(list(points), list(points.values()))
    if args.title:
        plt.title(args.title)
    if args.xlabel:
        plt.xlabel(args.xlabel)
    if args.ylabel:
        plt.ylabel(args.ylabel)
    plt.tight_layout()
    plt.savefig(args.out, dpi=150)
    plt.close()
    receipt.update(status="rendered", data_csv=data_csv,
                   png_sha256=sha256_file(args.out))
    _dump(args.out + ".receipt.json", receipt)
    print("FIGURE OK %s (%s, n=%d, excluded=%d)"
          % (args.out, args.kind, receipt["n_plotted"], n_excl))
    return 0


def extract_units_from_dict(dictionary):
    """从数据字典 JSON 提取 字段->单位；也兼容列名括号注记。"""
    units = {}
    if isinstance(dictionary, dict):
        for k, v in dictionary.items():
            if isinstance(v, dict) and v.get("unit"):
                units[str(k)] = str(v["unit"])
            else:
                m = UNIT_RE.search(str(k))
                if m:
                    units[str(k)] = m.group(1)
    elif isinstance(dictionary, list):
        for item in dictionary:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("column") or "")
                if item.get("unit"):
                    units[name] = str(item["unit"])
                else:
                    m = UNIT_RE.search(name)
                    if m:
                        units[name] = m.group(1)
    return units


def norm_unit(u):
    return re.sub(r"[\s\.\[\]\(\)]", "", str(u)).lower().replace("μ", "u")


def label_units(label):
    return [m.group(1) for m in UNIT_RE.finditer(label or "")]


def cmd_lint(args):
    dictionary = {}
    if args.dictionary:
        dictionary = json.load(open(args.dictionary, encoding="utf-8"))
    dict_units = {k: norm_unit(v) for k, v in extract_units_from_dict(dictionary).items()}
    violations = []
    checked = 0
    for rpath in args.receipts:
        if not os.path.isfile(rpath):
            violations.append("%s: receipt 文件不存在" % rpath)
            continue
        r = json.load(open(rpath, encoding="utf-8"))
        checked += 1
        tag = os.path.basename(r.get("out") or rpath)
        # 1) 列名必须真实存在于源表
        try:
            header, body = read_table(r["table"])
        except SystemExit as e:
            violations.append("%s: 源表不可读: %s" % (tag, e))
            continue
        for key in ("x_column", "y_column"):
            col = r.get(key)
            if col and col not in header:
                violations.append("%s: receipt 声称的列 %r 在源表中不存在" % (tag, col))
        # 2) PNG 存在性或 SKIPPED 诚实状态
        if r.get("status") == "rendered":
            out = r["out"]
            if not (os.path.isfile(out) and os.path.getsize(out) > 0):
                violations.append("%s: status=rendered 但 PNG 缺失或为空" % tag)
            elif r.get("png_sha256") and sha256_file(out) != r["png_sha256"]:
                violations.append("%s: PNG 哈希与 receipt 不符（渲染后被替换？）" % tag)
        elif r.get("status") != "SKIPPED_no_matplotlib":
            violations.append("%s: 未知 status %r" % (tag, r.get("status")))
        # 3) 值域与源表实测一致
        for col_key, range_key in (("x_column", "x_range"), ("y_column", "y_range")):
            col, rng = r.get(col_key), r.get(range_key)
            if col and rng and col in header:
                j = header.index(col)
                vals = [to_float(row[j] if j < len(row) else "") for row in body]
                vals = [v for v in vals if v is not None]
                if vals and (abs(min(vals) - rng[0]) > 1e-9 or abs(max(vals) - rng[1]) > 1e-9):
                    violations.append("%s: %s 值域 receipt=%s 源表实测=[%s, %s]"
                                      % (tag, col, rng, min(vals), max(vals)))
        # 4) 轴标签单位必须能在数据字典中找到
        if dict_units:
            known = set(dict_units.values())
            for lbl_key in ("xlabel", "ylabel"):
                for u in label_units(r.get(lbl_key)):
                    if norm_unit(u) not in known:
                        violations.append(
                            "%s: %s 中单位 (%s) 在数据字典中不存在；已知单位: %s"
                            % (tag, lbl_key, u, sorted(set(dict_units.values()))))
        # 5) 轴标签中的列名应与 receipt 列名一致（宽松：列名出现在标签里）
        for col_key, lbl_key in (("x_column", "xlabel"), ("y_column", "ylabel")):
            col, lbl = r.get(col_key), r.get(lbl_key)
            if col and lbl and col.lower() not in lbl.lower():
                violations.append("%s: %s=%r 未出现在轴标签 %r 中（轴与数据对不上？）"
                                  % (tag, lbl_key, lbl, col))
    if violations:
        print("FIGLINT FAIL（%d 项）:" % len(violations))
        for v in violations:
            print(" -", v)
        return 1
    print("FIGLINT PASS: %d 张图的回执全部通过（列名/PNG/值域/单位/轴标签一致）" % checked)
    return 0


def cmd_check(args):
    result = json.load(open(args.result, encoding="utf-8"))
    problems = []
    figs = result.get("figures") or result.get("figure_files") or []
    if isinstance(figs, str):
        figs = [figs]
    for item in figs:
        if isinstance(item, dict):
            path = item.get("path")
            status = item.get("status")
        else:
            path, status = item, None
        if not path:
            continue
        if status == "SKIPPED_no_matplotlib":
            if not os.path.isfile(path + ".data.csv"):
                problems.append("SKIPPED 图缺绘图数据 CSV: %s" % path)
            continue
        if not (os.path.isfile(path) and os.path.getsize(path) > 0):
            problems.append("图文件不存在或为空: %s" % path)
        elif path.lower().endswith(".png") and not os.path.isfile(path + ".receipt.json"):
            problems.append("PNG 缺 receipt（无法复核图与数据的一致性）: %s" % path)
    if problems:
        print("FIGCHECK FAIL（%d 项）:" % len(problems))
        for p in problems:
            print(" -", p)
        return 1
    print("FIGCHECK PASS: figures 字段 %d 项全部有文件与证据" % len(figs))
    return 0


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("render")
    p.add_argument("--table", required=True)
    p.add_argument("--kind", choices=["hist", "scatter", "bar", "line"], required=True)
    p.add_argument("--x", required=True)
    p.add_argument("--y")
    p.add_argument("--title")
    p.add_argument("--xlabel")
    p.add_argument("--ylabel")
    p.add_argument("--bins", type=int, default=20)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_render)
    p = sub.add_parser("lint")
    p.add_argument("--receipts", nargs="+", required=True)
    p.add_argument("--dictionary")
    p.set_defaults(fn=cmd_lint)
    p = sub.add_parser("check")
    p.add_argument("--result", required=True)
    p.set_defaults(fn=cmd_check)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
