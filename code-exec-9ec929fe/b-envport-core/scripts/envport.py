#!/usr/bin/env python3
"""envport.py — 零依赖可移植科研数据分析核心（纯 Python 标准库）。

重心是环境配置与可移植执行：同一命令在任何只有 Python ≥3.8 的机器上得到
逐字节相同的统计输出；第三方库（matplotlib）仅用于渲染，缺失时显式降级
并保留绘图数据，绝不中断交付。

子命令：
  env        环境快照：Python/平台/可用库版本/环境变量摘要，写入 provenance
  profile    CSV/SQLite 输入档案（sha256、编码、列类型、缺失、重复行）
  clean      按 rules.json 清洗：rename/coerce/missing/dedup/filter，逐条
             规则报告行数变化，引用不存在的列直接拒绝执行（防静默错误）
  describe   count/mean/median/std/min/max（缺失值默认不参与）
  aggregate  分组统计 group-by + metrics "col:mean,col:std,col:count"
  ttest      Welch 双样本 t 检验（纯 Python 不完全贝塔函数算 p 值）
  corr       Pearson r 与 p 值
  ols        1–2 自变量最小二乘回归（法方程解析解）
  sql        SQLite 只读查询（强制 SELECT/WITH，禁止写操作），0 行给出
             EMPTY RESULT 警告
  figure     hist/scatter/bar/line；每张图配 .receipt.json；无 matplotlib
             时写 SKIPPED_no_matplotlib 回执 + 绘图数据 CSV
  finalize   汇总 provenance（env + 输入哈希 + run_log）并做最低契约检查

每次调用追加一条 JSONL 到 --work/run_log.jsonl（命令、退出码、耗时），
相同输入必然得到相同输出：无随机源、无时间戳进入统计结果。
"""
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import sqlite3
import sys
import time

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--"}
RUN_LOG = None


def log_event(cmd, status, detail=None):
    if not RUN_LOG:
        return
    rec = {"cmd": cmd, "status": status, "detail": detail or {}}
    with open(RUN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


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
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    if not rows:
        raise SystemExit("EMPTY_TABLE: %s 无任何行" % path)
    header = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    return header, body


def to_float(v):
    s = str(v).strip()
    if s.lower() in MISSING:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def col_index(header, name):
    if name not in header:
        raise SystemExit("MISSING_COLUMN: 列 %r 不存在；可用列: %s"
                         % (name, ", ".join(header)))
    return header.index(name)


def numeric_column(header, body, name):
    j = col_index(header, name)
    vals = []
    for r in body:
        v = to_float(r[j] if j < len(r) else "")
        if v is not None:
            vals.append(v)
    return vals


def mean(xs):
    return sum(xs) / len(xs)


def sample_std(xs):
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else 0.0


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _betacf(a, b, x):
    """不完全贝塔函数的连分式（Numerical Recipes），用于 t 分布 p 值。"""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_sf(t, df):
    """t 分布双侧生存函数：P(|T| > |t|)。"""
    x = df / (df + t * t)
    return betai(df / 2.0, 0.5, x)


def cmd_env(args):
    info = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "stdlib_only": True,
        "optional_libs": {},
        "locale_env": {k: os.environ.get(k) for k in ("LANG", "LC_ALL", "TZ")},
    }
    for lib in ("matplotlib", "numpy", "pandas"):
        try:
            mod = __import__(lib)
            info["optional_libs"][lib] = getattr(mod, "__version__", "unknown")
        except ImportError:
            info["optional_libs"][lib] = None
    path = os.path.join(args.work, "env.json")
    _dump(path, info)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_profile(args):
    profs = []
    for p in args.paths:
        if p.lower().endswith((".db", ".sqlite", ".sqlite3")):
            profs.append(_profile_db(p))
        else:
            profs.append(_profile_csv(p))
    _dump(os.path.join(args.work, "profile.json"), {"inputs": profs})
    for p in profs:
        if p["kind"] == "csv":
            print("%s: %d 行 %d 列, 重复行 %d, sha256=%s..."
                  % (p["file"], p["n_rows"], p["n_cols"],
                     p["exact_duplicate_rows"], p["sha256"][:12]))
        else:
            print("%s: 表 %s, sha256=%s..."
                  % (p["file"], [t["table"] for t in p["tables"]], p["sha256"][:12]))
    return 0


def _profile_csv(path):
    header, body = read_table(path)
    seen, dups = set(), 0
    for r in body:
        k = tuple(r)
        if k in seen:
            dups += 1
        seen.add(k)
    cols = []
    for j, name in enumerate(header):
        raw = [(r[j].strip() if j < len(r) else "") for r in body]
        miss = sum(1 for v in raw if v.lower() in MISSING)
        vals = [to_float(v) for v in raw]
        nums = [v for v in vals if v is not None]
        numeric = len(nums) == len(vals) - miss and nums
        c = {"name": name, "n_missing": miss,
             "dtype": "float" if numeric else "str"}
        if numeric:
            c.update(min=min(nums), max=max(nums))
        else:
            c["n_distinct"] = len({v for v in raw if v.lower() not in MISSING})
        cols.append(c)
    return {"file": path, "kind": "csv", "sha256": sha256_file(path),
            "n_rows": len(body), "n_cols": len(header),
            "exact_duplicate_rows": dups, "columns": cols}


def _profile_db(path):
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        tables = []
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            n = con.execute('SELECT COUNT(*) FROM "%s"' % t.replace('"', '""')).fetchone()[0]
            cols = [{"name": r[1], "type": r[2]}
                    for r in con.execute('PRAGMA table_info("%s")' % t.replace('"', '""'))]
            tables.append({"table": t, "n_rows": n, "columns": cols})
    finally:
        con.close()
    return {"file": path, "kind": "sqlite", "sha256": sha256_file(path), "tables": tables}


def cmd_clean(args):
    rules = json.load(open(args.rules, encoding="utf-8"))
    header, body = read_table(args.table)
    n0 = len(body)
    report = {"input": args.table, "input_sha256": sha256_file(args.table),
              "raw_rows": n0, "steps": []}

    rename = rules.get("rename", {})
    for old in rename:
        col_index(header, old)  # 不存在即拒绝执行
    header = [rename.get(h, h) for h in header]
    report["steps"].append({"rule": "rename", "applied": rename})

    keep = rules.get("select_columns")
    if keep:
        idx = [col_index(header, c) for c in keep]
        header = [header[i] for i in idx]
        body = [[r[i] if i < len(r) else "" for i in idx] for r in body]
        report["steps"].append({"rule": "select_columns", "kept": len(idx)})

    for col, _typ in rules.get("coerce", {}).items():
        j = col_index(header, col)
        bad = 0
        for r in body:
            v = r[j] if j < len(r) else ""
            if v.strip().lower() not in MISSING and to_float(v) is None:
                r[j] = ""
                bad += 1
        report["steps"].append({"rule": "coerce", "column": col,
                                "unparseable_set_to_missing": bad})

    miss = rules.get("missing", {})
    policy = miss.get("policy", "report_only")
    mcols = miss.get("columns") or header
    for c in mcols:
        col_index(header, c)
    if policy == "drop_rows":
        idx = [col_index(header, c) for c in mcols]
        before = len(body)
        body = [r for r in body
                if not any((r[j] if j < len(r) else "").strip().lower() in MISSING
                           for j in idx)]
        report["steps"].append({"rule": "missing.drop_rows", "columns": mcols,
                                "rows_dropped": before - len(body)})
    elif policy == "impute":
        for col, how in miss.get("impute", {}).items():
            j = col_index(header, col)
            vals = [to_float(r[j]) for r in body]
            nums = [v for v in vals if v is not None]
            if how == "mean":
                fill = mean(nums)
            elif how == "median":
                fill = median(nums)
            else:
                fill = how  # 字面值
            n_imp = 0
            for r in body:
                if to_float(r[j]) is None:
                    r[j] = str(fill)
                    n_imp += 1
            report["steps"].append({"rule": "missing.impute", "column": col,
                                    "method": how, "n_imputed": n_imp})
    else:
        report["steps"].append({"rule": "missing.report_only",
                                "note": "缺失行保留；统计命令默认忽略缺失值"})

    dedup = rules.get("dedup", {})
    if dedup.get("policy") == "drop_exact":
        before = len(body)
        seen, nb = set(), []
        for r in body:
            k = tuple(r)
            if k not in seen:
                seen.add(k)
                nb.append(r)
        body = nb
        report["steps"].append({"rule": "dedup.drop_exact",
                                "rows_dropped": before - len(body)})
    elif dedup.get("policy") == "drop_by":
        keys = dedup.get("keys", [])
        idx = [col_index(header, c) for c in keys]
        before = len(body)
        seen, nb = set(), []
        for r in body:
            k = tuple(r[j] for j in idx)
            if k not in seen:
                seen.add(k)
                nb.append(r)
        body = nb
        report["steps"].append({"rule": "dedup.drop_by", "keys": keys,
                                "rows_dropped": before - len(body)})

    for f in rules.get("filter", []):
        j = col_index(header, f["column"])
        op, val = f["op"], f.get("value")
        before = len(body)
        body = [r for r in body if _apply_filter(r[j] if j < len(r) else "", op, val)]
        report["steps"].append({"rule": "filter", "column": f["column"], "op": op,
                                "value": val, "rows_dropped": before - len(body)})

    report["final_rows"] = len(body)
    with open(args.out, "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(header)
        w.writerows(body)
    _dump(args.report, report)
    print("CLEAN OK %d -> %d 行 -> %s (报告 %s)"
          % (n0, len(body), args.out, args.report))
    return 0


def _apply_filter(v, op, val):
    s = str(v).strip()
    if op == "na":
        return s.lower() in MISSING
    if op == "notna":
        return s.lower() not in MISSING
    fv, fval = to_float(s), to_float(val)
    if op == "==":
        return s == str(val)
    if op == "!=":
        return s != str(val)
    if fv is None or fval is None:
        return False
    return {">": fv > fval, ">=": fv >= fval, "<": fv < fval,
            "<=": fv <= fval}.get(op, False)


def cmd_describe(args):
    header, body = read_table(args.table)
    out = {}
    for name in args.columns.split(","):
        name = name.strip()
        vals = numeric_column(header, body, name)
        if not vals:
            out[name] = {"n": 0, "warning": "NO_NUMERIC_VALUES"}
            continue
        out[name] = {"n": len(vals), "mean": mean(vals), "median": median(vals),
                     "std": sample_std(vals), "min": min(vals), "max": max(vals),
                     "n_rows_total": len(body),
                     "n_excluded_missing": len(body) - len(vals)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_aggregate(args):
    header, body = read_table(args.table)
    gj = col_index(header, args.group_by)
    metrics = []
    for m in args.metrics.split(","):
        col, fn = m.strip().split(":")
        col_index(header, col)
        metrics.append((col, fn))
    groups = {}
    for r in body:
        groups.setdefault(r[gj], []).append(r)
    out = {}
    for g, rows in sorted(groups.items()):
        rec = {"n_rows": len(rows)}
        for col, fn in metrics:
            vals = numeric_column(header, rows, col)
            rec["%s_%s" % (col, fn)] = _aggfn(vals, fn)
        out[g] = rec
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _aggfn(vals, fn):
    if not vals:
        return None
    return {"mean": mean, "median": median, "std": sample_std,
            "min": min, "max": max, "count": len, "sum": sum}[fn](vals)


def cmd_ttest(args):
    header, body = read_table(args.table)
    gj = col_index(header, args.group)
    groups = {}
    for r in body:
        v = to_float(r[col_index(header, args.column)])
        if v is not None:
            groups.setdefault(r[gj], []).append(v)
    if len(groups) != 2:
        raise SystemExit("TTEST_NEEDS_2_GROUPS: 实际 %d 组 %s"
                         % (len(groups), sorted(groups)))
    (g1, x), (g2, y) = sorted(groups.items())
    if len(x) < 2 or len(y) < 2:
        raise SystemExit("TTEST_GROUP_TOO_SMALL")
    m1, m2 = mean(x), mean(y)
    v1, v2 = sample_std(x) ** 2, sample_std(y) ** 2
    se2 = v1 / len(x) + v2 / len(y)
    if se2 == 0:
        raise SystemExit("TTEST_ZERO_VARIANCE: 两组方差均为 0，检验无意义")
    t = (m1 - m2) / math.sqrt(se2)
    df = se2 ** 2 / ((v1 / len(x)) ** 2 / (len(x) - 1) + (v2 / len(y)) ** 2 / (len(y) - 1))
    out = {"test": "welch_ttest", "groups": {g1: {"n": len(x), "mean": m1},
                                             g2: {"n": len(y), "mean": m2}},
           "t": t, "df": df, "p_two_sided": t_sf(abs(t), df),
           "assumptions_checked": " Welch 检验不要求等方差；正态性未自动检查，报告时须注明"}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_corr(args):
    header, body = read_table(args.table)
    jx, jy = col_index(header, args.x), col_index(header, args.y)
    pairs = [(to_float(r[jx]), to_float(r[jy])) for r in body]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if n < 3:
        raise SystemExit("CORR_TOO_FEW_PAIRS: %d" % n)
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = mean(xs), mean(ys)
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx == 0 or syy == 0:
        raise SystemExit("CORR_ZERO_VARIANCE")
    r = sum((a - mx) * (b - my) for a, b in pairs) / math.sqrt(sxx * syy)
    t = r * math.sqrt((n - 2) / max(1e-300, 1 - r * r))
    out = {"x": args.x, "y": args.y, "n_pairs": n, "pearson_r": r,
           "p_two_sided": t_sf(abs(t), n - 2),
           "n_excluded_missing": len(body) - n}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_ols(args):
    header, body = read_table(args.table)
    ycol = col_index(header, args.y)
    xcols = [col_index(header, c.strip()) for c in args.x.split(",")]
    rows = []
    for r in body:
        vals = [to_float(r[ycol])] + [to_float(r[j]) for j in xcols]
        if all(v is not None for v in vals):
            rows.append(vals)
    n = len(rows)
    p = len(xcols) + 1
    if n < p + 1:
        raise SystemExit("OLS_TOO_FEW_ROWS: n=%d, p=%d" % (n, p))
    # 设计矩阵 [1, x1, x2]，法方程 (X'X)b = X'y，高斯消元
    X = [[1.0] + r[1:] for r in rows]
    y = [r[0] for r in rows]
    XtX = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(p)] for i in range(p)]
    Xty = [sum(X[k][i] * y[k] for k in range(n)) for i in range(p)]
    beta = _solve(XtX, Xty)
    resid = [y[k] - sum(beta[i] * X[k][i] for i in range(p)) for k in range(n)]
    sse = sum(e * e for e in resid)
    r2 = 1 - sse / sum((v - mean(y)) ** 2 for v in y)
    out = {"y": args.y, "x": args.x.split(","), "n": n,
           "coefficients": {"intercept": beta[0],
                            **{c.strip(): beta[i + 1] for i, c in enumerate(args.x.split(","))}},
           "r_squared": r2, "residual_sse": sse,
           "n_excluded_missing": len(body) - n}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _solve(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            raise SystemExit("OLS_SINGULAR: 设计矩阵奇异（自变量共线？）")
        M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [M[r][k] - f * M[c][k] for k in range(n + 1)]
    return [M[i][n] / M[i][i] for i in range(n)]


def cmd_sql(args):
    q = args.query.strip().rstrip(";")
    first = q.split(None, 1)[0].upper() if q.split() else ""
    if first not in ("SELECT", "WITH", "PRAGMA"):
        raise SystemExit("SQL_READONLY: 仅允许 SELECT/WITH/PRAGMA，拒绝: %s" % first)
    con = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)
    try:
        cur = con.execute(q)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchall()
    except sqlite3.Error as e:
        raise SystemExit("SQL_FAILED: %s —— 核对表名/列名/连接键后重试，不得改库" % e)
    finally:
        con.close()
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
    if not rows:
        print("WARNING EMPTY RESULT: 查询返回 0 行。先核对表名、连接键与 WHERE "
              "条件（漏一个字段会导致行数偏多/偏少），确认无误再把空结果当答案。")
    print(json.dumps({"columns": cols, "n_rows": len(rows),
                      "rows_preview": [list(r) for r in rows[:20]]},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_figure(args):
    header, body = read_table(args.table)
    receipt = {"tool": "envport figure", "kind": args.kind, "table": args.table,
               "table_sha256": sha256_file(args.table), "out": args.out,
               "title": args.title, "xlabel": args.xlabel, "ylabel": args.ylabel}
    try:
        if os.environ.get("ENVPORT_NO_MPL"):
            raise ImportError("forced by ENVPORT_NO_MPL")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        data_csv = args.out + ".data.csv"
        _export_plot_data(data_csv, header, body, args)
        receipt.update(status="SKIPPED_no_matplotlib", data_csv=data_csv,
                       note="渲染库不可用；绘图数据已保存，可在有 matplotlib 的环境复绘。"
                            " result.json 中须如实报告图未渲染，不得交付不存在的图。")
        _dump(args.out + ".receipt.json", receipt)
        print("FIGURE SKIPPED_no_matplotlib: 数据已存 %s" % data_csv)
        return 0

    jx = col_index(header, args.x)
    xs_raw = [(r[jx] if jx < len(r) else "") for r in body]
    n_drop = 0
    if args.kind == "hist":
        xs = []
        for v in xs_raw:
            f = to_float(v)
            if f is None:
                n_drop += 1
            else:
                xs.append(f)
        plt.figure()
        plt.hist(xs, bins=args.bins)
    elif args.kind in ("scatter", "line"):
        jy = col_index(header, args.y)
        xs, ys = [], []
        for r in body:
            a = to_float(r[jx] if jx < len(r) else "")
            b = to_float(r[jy] if jy < len(r) else "")
            if a is None or b is None:
                n_drop += 1
                continue
            xs.append(a)
            ys.append(b)
        plt.figure()
        if args.kind == "scatter":
            plt.scatter(xs, ys, s=8)
        else:
            order = sorted(range(len(xs)), key=lambda i: xs[i])
            plt.plot([xs[i] for i in order], [ys[i] for i in order])
    elif args.kind == "bar":
        counts = {}
        for v in xs_raw:
            s = v.strip()
            if s.lower() in MISSING:
                n_drop += 1
                continue
            counts[s] = counts.get(s, 0) + 1
        plt.figure()
        plt.bar(list(counts), list(counts.values()))
        receipt["categories"] = counts
    else:
        raise SystemExit("FIGURE_KIND_UNKNOWN: %s" % args.kind)
    if args.title:
        plt.title(args.title)
    if args.xlabel:
        plt.xlabel(args.xlabel)
    if args.ylabel:
        plt.ylabel(args.ylabel)
    plt.tight_layout()
    plt.savefig(args.out, dpi=150)
    plt.close()
    receipt.update(status="rendered", n_points=(len(xs) if args.kind != "bar"
                                                else sum(receipt["categories"].values())),
                   n_excluded_missing=n_drop)
    _dump(args.out + ".receipt.json", receipt)
    print("FIGURE OK %s (%s, receipt %s)" % (args.out, args.kind, args.out + ".receipt.json"))
    return 0


def _export_plot_data(path, header, body, args):
    cols = [args.x] + ([args.y] if getattr(args, "y", None) else [])
    idx = [col_index(header, c) for c in cols]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in body:
            w.writerow([r[j] if j < len(r) else "" for j in idx])


def cmd_finalize(args):
    case_id = None
    cj = os.path.join(args.input, "case.json")
    fields = []
    if os.path.isfile(cj):
        case = json.load(open(cj, encoding="utf-8"))
        case_id = case.get("case_id") or case.get("id")
        oc = case.get("output_contract") or {}
        if isinstance(oc, dict):
            oc = oc.get("fields") or oc.get("required") or list(oc)
        fields = [f if isinstance(f, str) else f.get("name") for f in oc]
    rpath = os.path.join(args.output, "result.json")
    result = json.load(open(rpath, encoding="utf-8")) if os.path.isfile(rpath) else {}
    problems = []
    if case_id and result.get("case_id") != case_id:
        problems.append("case_id 不一致")
    for k in fields:
        if result.get(k) is None:
            problems.append("契约字段为 null: %s" % k)
    env = {}
    ep = os.path.join(args.work, "env.json")
    if os.path.isfile(ep):
        env = json.load(open(ep, encoding="utf-8"))
    result.setdefault("provenance", {}).update({
        "environment": env, "run_log": os.path.join(args.work, "run_log.jsonl"),
        "determinism": "纯 stdlib 计算，无随机源；相同输入得到相同输出"})
    if problems and result.get("status") == "success":
        result["status"] = "partial"
        result.setdefault("missing_fields", [])
        known = {m.get("field") for m in result["missing_fields"] if isinstance(m, dict)}
        for p in problems:
            f = p.split(": ")[-1]
            if f not in known:
                result["missing_fields"].append({"field": f, "reason": p})
    _dump(rpath, result)
    if problems:
        print("FINALIZE partial（%d 项待补）: %s" % (len(problems), "; ".join(problems)))
        return 1
    print("FINALIZE OK: status=success, provenance 已并入 env/run_log")
    return 0


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def main():
    global RUN_LOG
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default=".")
    ap.add_argument("--output", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        p = sub.add_parser(name, **kw)
        p.set_defaults(fn=fn)
        return p

    add("env", cmd_env)
    p = add("profile", cmd_profile)
    p.add_argument("paths", nargs="+")
    p = add("clean", cmd_clean)
    p.add_argument("--table", required=True)
    p.add_argument("--rules", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--report", required=True)
    p = add("describe", cmd_describe)
    p.add_argument("--table", required=True)
    p.add_argument("--columns", required=True)
    p = add("aggregate", cmd_aggregate)
    p.add_argument("--table", required=True)
    p.add_argument("--group-by", required=True)
    p.add_argument("--metrics", required=True)
    p = add("ttest", cmd_ttest)
    p.add_argument("--table", required=True)
    p.add_argument("--column", required=True)
    p.add_argument("--group", required=True)
    p = add("corr", cmd_corr)
    p.add_argument("--table", required=True)
    p.add_argument("--x", required=True)
    p.add_argument("--y", required=True)
    p = add("ols", cmd_ols)
    p.add_argument("--table", required=True)
    p.add_argument("--y", required=True)
    p.add_argument("--x", required=True)
    p = add("sql", cmd_sql)
    p.add_argument("--db", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--out")
    p = add("figure", cmd_figure)
    p.add_argument("--table", required=True)
    p.add_argument("--kind", choices=["hist", "scatter", "bar", "line"], required=True)
    p.add_argument("--x", required=True)
    p.add_argument("--y")
    p.add_argument("--title")
    p.add_argument("--xlabel")
    p.add_argument("--ylabel")
    p.add_argument("--bins", type=int, default=20)
    p.add_argument("--out", required=True)
    p = add("finalize", cmd_finalize)
    p.add_argument("--input", required=True)

    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)
    RUN_LOG = os.path.join(args.work, "run_log.jsonl")
    t0 = time.time()
    try:
        rc = args.fn(args)
    except SystemExit as e:
        log_event(args.cmd, "error", {"message": str(e)})
        raise
    log_event(args.cmd, "ok", {"elapsed_s": round(time.time() - t0, 3)})
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
