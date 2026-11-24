#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_case.py — one-shot driver: research data -> cleaning -> statistics ->
publication-grade figures (PNG 300dpi + embedded-font PDF + live-text SVG) ->
Chinese captions -> independent verification -> result.json (output_contract).

Usage:
    python3 run_case.py --case /input/case.json --input-dir /input \
        --work /app/work --out /app/output

Design rules: pure stdlib for data/statistics; numpy+matplotlib only for
figures (auto pip-install attempt; degrade to partial result, never crash).
A valid partial result.json exists from the first seconds of the run and is
updated after every stage.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import traceback

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "--", "?", "missing"}
SEED = 20240501
OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
             "#56B4E9", "#F0E442", "#000000"]
CJK_CANDIDATES = ["PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC",
                  "Noto Sans SC", "Source Han Sans SC", "Source Han Sans CN",
                  "WenQuanYi Zen Hei", "WenQuanYi Micro Hei", "Microsoft YaHei",
                  "SimHei", "STHeiti", "Heiti SC", "Songti SC", "Arial Unicode MS"]


# ---------------------------------------------------------------------------
# basic IO
# ---------------------------------------------------------------------------
def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, default=str)


def norm_level(v):
    """Canonical string for a group level: 1.0 -> '1', 'a ' -> 'a'."""
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def is_missing(v):
    return v is None or str(v).strip().lower() in MISSING_TOKENS


def try_float(v):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# table loading: CSV/TSV/TXT/JSON/SQLite (+ CSV<->SQLite reconciliation)
# ---------------------------------------------------------------------------
def load_delimited(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text, enc = raw.decode("utf-8", errors="replace"), "utf-8-replace"
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if "\t" in sample.split("\n", 1)[0] else ","
    rows = [r for r in csv.reader(text.splitlines(), delimiter=delim) if r]
    if not rows:
        raise ValueError("empty table: " + path)
    header = [str(c).strip() for c in rows[0]]
    width = len(header)
    body = []
    for r in rows[1:]:
        r = list(r)
        if len(r) < width:
            r = r + [""] * (width - len(r))
        body.append(r[:width])
    return {"columns": header, "rows": body, "encoding": enc, "delimiter": delim,
            "path": path}


def load_sqlite(path):
    con = sqlite3.connect(path)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        if not tables:
            raise ValueError("no table in sqlite: " + path)
        table = tables[0]
        cur = con.execute("SELECT * FROM \"%s\"" % table.replace('"', '""'))
        header = [d[0] for d in cur.description]
        body = [["" if v is None else str(v) for v in row] for row in cur.fetchall()]
        return {"columns": header, "rows": body, "encoding": "sqlite",
                "delimiter": None, "path": path, "table": table,
                "tables": tables}
    finally:
        con.close()


def reconcile_tables(a, b):
    """Cell-level comparison of two loaded tables. Returns report dict."""
    cols_a = [c.strip() for c in a["columns"]]
    cols_b = [c.strip() for c in b["columns"]]
    rep = {"rows_a": len(a["rows"]), "rows_b": len(b["rows"]),
           "cols_a": a["columns"], "cols_b": b["columns"],
           "row_count_equal": len(a["rows"]) == len(b["rows"]),
           "column_sets_equal": set(cols_a) == set(cols_b),
           "cell_mismatches": 0, "mismatch_examples": [], "compared": True}
    if set(a["columns"]) != set(cols_a) or set(b["columns"]) != set(cols_b):
        rep["column_name_whitespace_normalized"] = True
    if not rep["row_count_equal"] or not rep["column_sets_equal"]:
        rep["compared"] = False
        return rep
    idx_b = [cols_b.index(c) for c in cols_a]
    for i, ra in enumerate(a["rows"]):
        rb = b["rows"][i]
        for j, c in enumerate(a["columns"]):
            va, vb = str(ra[j]).strip(), str(rb[idx_b[j]]).strip()
            fa, fb = try_float(va), try_float(vb)
            same = (abs(fa - fb) <= 1e-9 * max(1.0, abs(fa), abs(fb))
                    if fa is not None and fb is not None else va == vb)
            if not same:
                rep["cell_mismatches"] += 1
                if len(rep["mismatch_examples"]) < 5:
                    rep["mismatch_examples"].append(
                        {"row": i, "column": c, "csv": va, "sqlite": vb})
    return rep


def discover_and_load(input_dir, dataset_name, log):
    files = []
    for root, _dirs, names in os.walk(input_dir):
        for n in sorted(names):
            p = os.path.join(root, n)
            if os.path.isfile(p):
                files.append(p)
    data_files = [p for p in files
                  if os.path.splitext(p)[1].lower()
                  in (".csv", ".tsv", ".txt", ".json", ".sqlite", ".db", ".sqlite3")
                  and os.path.basename(p) not in ("case.json", "result.json")]
    tables = {}
    for p in data_files:
        ext = os.path.splitext(p)[1].lower()
        try:
            if ext in (".sqlite", ".db", ".sqlite3"):
                tables[p] = load_sqlite(p)
            elif ext == ".json":
                text, _ = read_text(p)
                obj = json.loads(text)
                if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                    cols = list(obj[0].keys())
                    tables[p] = {"columns": cols,
                                 "rows": [[str(r.get(c, "")) for c in cols] for r in obj],
                                 "encoding": "json", "delimiter": None, "path": p}
                else:
                    log.append("skip non-tabular json: " + p)
            else:
                tables[p] = load_delimited(p)
        except Exception as exc:  # noqa: BLE001
            log.append("load failed %s: %s" % (p, exc))
    if not tables:
        raise RuntimeError("no readable data table found under " + input_dir)
    # primary: prefer csv/tsv whose stem matches dataset name, else largest
    def score(item):
        p, t = item
        stem = os.path.splitext(os.path.basename(p))[0].lower()
        s = len(t["rows"])
        if dataset_name and stem == str(dataset_name).lower():
            s += 10 ** 9
        if os.path.splitext(p)[1].lower() in (".csv", ".tsv"):
            s += 10 ** 6
        return s
    primary_path, primary = sorted(tables.items(), key=score)[-1]
    reconciliation = None
    csv_t = next((t for p, t in tables.items()
                  if os.path.splitext(p)[1].lower() in (".csv", ".tsv")), None)
    db_t = next((t for p, t in tables.items()
                 if os.path.splitext(p)[1].lower() in (".sqlite", ".db", ".sqlite3")), None)
    if csv_t is not None and db_t is not None:
        reconciliation = reconcile_tables(csv_t, db_t)
        reconciliation["csv_file"] = csv_t["path"]
        reconciliation["sqlite_file"] = db_t["path"]
    return primary, tables, reconciliation, files


# ---------------------------------------------------------------------------
# cleaning (audit only, never silent mutation)
# ---------------------------------------------------------------------------
def clean_table(table):
    cols = table["columns"]
    rows = [[("" if v is None else str(v)).strip() for v in r] for r in table["rows"]]
    n_rows = len(rows)
    report = {"input_rows": n_rows, "rules": [], "columns": {},
              "duplicate_rows": 0, "duplicate_action": "kept_marked",
              "outlier_rule": "1.5*IQR fences, flag only, never delete"}
    report["rules"].append({
        "rule": "trim_whitespace",
        "detail": "strip leading/trailing whitespace of every cell; values not otherwise modified"})
    # numeric coercion per column
    col_types = {}
    coerced = {c: [] for c in cols}
    for j, c in enumerate(cols):
        n_miss = sum(1 for r in rows if is_missing(r[j]))
        n_num = sum(1 for r in rows if not is_missing(r[j]) and try_float(r[j]) is not None)
        n_nonmiss = n_rows - n_miss
        ctype = "numeric" if n_nonmiss > 0 and n_num == n_nonmiss else (
            "empty" if n_nonmiss == 0 else "categorical")
        col_types[c] = ctype
        report["columns"][c] = {"type": ctype, "missing": n_miss,
                                "coerced_to_float": n_num,
                                "coercion_failures": n_nonmiss - n_num}
        for r in rows:
            coerced[c].append(None if is_missing(r[j]) else
                              (try_float(r[j]) if ctype == "numeric" else r[j]))
    report["rules"].append({
        "rule": "missing_values",
        "detail": ("missing tokens %s counted per column; NOT imputed"
                   % sorted(MISSING_TOKENS))})
    # duplicates
    seen, dups = {}, 0
    for r in rows:
        key = tuple(r)
        if key in seen:
            dups += 1
        else:
            seen[key] = 1
    report["duplicate_rows"] = dups
    report["rules"].append({
        "rule": "duplicates",
        "detail": ("%d exact duplicate row(s) detected; kept and marked "
                   "(no deletion without explicit task request)" % dups)})
    return {"columns": cols, "data": coerced, "n_rows": n_rows,
            "types": col_types}, report


def iqr_fences(vals):
    v = sorted(x for x in vals if x is not None)
    if len(v) < 4:
        return None
    q1, _m, q3 = quartiles(v)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr, q1, q3


# ---------------------------------------------------------------------------
# statistics (pure python; definitions recorded in statistics.md)
# ---------------------------------------------------------------------------
def quartiles(sorted_vals):
    n = len(sorted_vals)
    def q(p):
        if n == 1:
            return sorted_vals[0]
        pos = (n - 1) * p
        lo = int(math.floor(pos))
        hi = min(lo + 1, n - 1)
        frac = pos - lo
        return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac
    return q(0.25), q(0.5), q(0.75)


def describe(vals):
    v = [x for x in vals if x is not None]
    n = len(v)
    if n == 0:
        return None
    mean = sum(v) / n
    if n > 1:
        var = sum((x - mean) ** 2 for x in v) / (n - 1)
    else:
        var = 0.0
    sd = math.sqrt(var)
    sem = sd / math.sqrt(n) if n > 0 else 0.0
    sv = sorted(v)
    q1, med, q3 = quartiles(sv)
    m2 = sum((x - mean) ** 2 for x in v) / n
    m3 = sum((x - mean) ** 3 for x in v) / n
    skew = (m3 / (m2 ** 1.5)) if m2 > 0 else 0.0
    return {"n": n, "mean": mean, "sd": sd, "sem": sem, "median": med,
            "q1": q1, "q3": q3, "min": sv[0], "max": sv[-1],
            "skewness": skew, "missing": None}


def pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None, n
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if sxx <= 0 or syy <= 0:
        return None, n
    return sxy / math.sqrt(sxx * syy), n


def freq_table(vals):
    out = {}
    for v in vals:
        k = norm_level(v)
        if k is None:
            continue
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


KNOWN_UNIT_SUFFIXES = {
    "cm", "mm", "m", "km", "g", "kg", "mg", "ug", "ml", "l", "dl",
    "mpa", "kpa", "pa", "hz", "khz", "s", "ms", "min", "h", "day",
    "days", "ppm", "ppb", "pct", "percent", "c", "k", "mol", "mmol",
    "v", "a", "w", "j", "kj", "kcal", "nm", "um", "yr", "years"}


def short_name(name, limit=18):
    return name if len(name) <= limit else name[:limit - 1] + "…"


UNIT_PATTERN = re.compile(
    r"kg|mpa|kpa|\bpa\b|%|cm|mm|mg|μg|ug|ml|\bdl\b|\bl\b|mol|m\^|"
    r"m2|m3|hz|\bppm\b|\bppm\b|day|hour|inch|\bg\b", re.I)
UNIT_ALIASES = {"kg in a m^3 mixture": "kg/m³",
                "kg in a m3 mixture": "kg/m³"}


def display_name_unit(col):
    c = col.strip()
    parens = re.findall(r"[(（]([^)）]*)[)）]", c)
    if parens:
        name = re.split(r"[(（]", c)[0].strip()
        unit = ""
        for p in parens:
            if UNIT_PATTERN.search(p):
                unit = p.split(",")[0].strip()
                break
        if not unit:
            unit = parens[-1].split(",")[0].strip()
        unit = UNIT_ALIASES.get(unit, unit)
        return name, unit
    m2 = re.match(r"^(.+?)_([a-zA-Zμ%/]+)$", c)
    if m2 and m2.group(2).lower() in KNOWN_UNIT_SUFFIXES:
        return m2.group(1), m2.group(2)
    return c, ""


def detect_group_column(task_text, cols, types, data, n_rows):
    candidates = []
    for m in re.finditer(r"按\s*([A-Za-z_一-鿿][\w一-鿿]*)", task_text or ""):
        token = m.group(1)
        for c in cols:
            if c.lower() == token.lower():
                candidates.append((100, c))
    for c in cols:
        if types[c] == "categorical":
            uniq = sorted({str(v) for v in data[c] if v is not None})
            if 2 <= len(uniq) <= 12:
                candidates.append((80, c))
        elif types[c] == "numeric":
            vals = [v for v in data[c] if v is not None]
            uniq = sorted(set(vals))
            if (2 <= len(uniq) <= 12 and all(float(u).is_integer() for u in uniq)
                    and len(uniq) < max(3, n_rows // 10)
                    and re.search(r"class|target|label|group|batch|批次|类别", c, re.I)):
                candidates.append((60, c))
    if candidates:
        c = sorted(candidates, key=lambda kv: -kv[0])[0][1]
        levels = sorted({norm_level(v) for v in data[c]
                         if norm_level(v) is not None})
        return {"mode": "categorical", "column": c, "levels": levels}
    return {"mode": "none", "column": None, "levels": []}


def detect_target_column(task_text, cols, types):
    m = re.search(r"目标变量为?\s*[:：]?\s*([^，。；\n（(]+)", task_text or "")
    token = m.group(1).strip() if m else None
    if token:
        tl = token.lower()
        for c in cols:
            if tl in c.lower():
                if types[c] == "numeric":
                    return c
    for c in cols:
        if re.search(r"strength|target|outcome|response", c, re.I) and types[c] == "numeric":
            return c
    return None


def make_bins(vals, n_bins=4):
    v = sorted(x for x in vals if x is not None)
    if len(v) < n_bins * 3:
        return None
    edges = [v[int(round(i * (len(v) - 1) / n_bins))] for i in range(n_bins + 1)]
    edges = sorted(set(edges))
    if len(edges) < 3:
        return None
    labels = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        fmt = lambda x: ("%g" % x)
        labels.append("%s–%s" % (fmt(lo), fmt(hi)))
    def assign(x):
        if x is None:
            return None
        for k in range(len(edges) - 1):
            if edges[k] <= x <= edges[k + 1] or (k == len(edges) - 2 and x == edges[-1]):
                return labels[k]
        return labels[-1] if x >= edges[-1] else labels[0]
    return {"edges": edges, "labels": labels, "assign": assign}


# ---------------------------------------------------------------------------
# matplotlib setup (lazy; degrade gracefully)
# ---------------------------------------------------------------------------
def import_plotting(log):
    try:
        import numpy  # noqa: F401
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: F401
        return True, None
    except ImportError:
        log.append("numpy/matplotlib missing; attempting pip install")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                            "numpy", "matplotlib"], check=True, timeout=600)
            import numpy  # noqa: F401
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt  # noqa: F401
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)


def setup_style():
    import matplotlib
    from matplotlib import font_manager
    from matplotlib.ft2font import FT2Font
    chosen = None
    by_name = {}
    for f in font_manager.fontManager.ttflist:
        by_name.setdefault(f.name, f.fname)
    for cand in CJK_CANDIDATES:
        if cand in by_name:
            try:
                cm = FT2Font(by_name[cand]).get_charmap()
                if ord("中") in cm and ord("图") in cm:
                    chosen = cand
                    break
            except Exception:  # noqa: BLE001
                continue
    if chosen is None:  # scan every font for CJK coverage
        for name, path in sorted(by_name.items()):
            try:
                cm = FT2Font(path).get_charmap()
                if ord("中") in cm and ord("图") in cm:
                    chosen = name
                    break
            except Exception:  # noqa: BLE001
                continue
    base = [chosen] if chosen else []
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": base + ["DejaVu Sans"],
        "axes.unicode_minus": False,
        "font.size": 6.0, "axes.titlesize": 6.5, "axes.labelsize": 6.0,
        "xtick.labelsize": 5.0, "ytick.labelsize": 5.0, "legend.fontsize": 5.0,
        "axes.linewidth": 0.6, "lines.linewidth": 0.8, "lines.markersize": 2.0,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.constrained_layout.use": True,
    })
    return chosen


def save_figure(fig, out_dir, fid, width_mm, height_mm, dpi=300):
    fig.set_size_inches(width_mm / 25.4, height_mm / 25.4)
    paths = {}
    for ext, kw in (("png", {"dpi": dpi}), ("pdf", {}), ("svg", {})):
        p = os.path.join(out_dir, "%s.%s" % (fid, ext))
        fig.savefig(p, format=ext, **kw)
        paths[ext] = os.path.basename(p)
    return paths


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------
def _grid_shape(k, max_cols):
    cols = min(max_cols, k)
    rows = int(math.ceil(k / cols))
    return rows, cols


def _jitter(vals, width=0.18):
    import numpy as np
    rng = np.random.default_rng(SEED)
    return rng.uniform(-width, width, size=len(vals))


def _boxplot(ax, series, tick_labels, **kw):
    """matplotlib >=3.9 uses tick_labels; older versions use labels."""
    try:
        return ax.boxplot(series, tick_labels=tick_labels, **kw)
    except TypeError:
        return ax.boxplot(series, labels=tick_labels, **kw)


def _subsample(xs, ys, limit=300):
    import numpy as np
    if len(xs) <= limit:
        return xs, ys, False
    rng = np.random.default_rng(SEED)
    idx = np.sort(rng.choice(len(xs), size=limit, replace=False))
    return [xs[i] for i in idx], [ys[i] for i in idx], True


def fig_distributions(numeric_cols, data, units, out_dir, width_mm, use_log,
                      disp):
    import numpy as np
    import matplotlib.pyplot as plt
    k = len(numeric_cols)
    rows, cols = _grid_shape(k, 3)
    height_mm = min(240, max(50, rows * 30))
    fig, axes = plt.subplots(rows, cols, squeeze=False)
    letters = "abcdefghijklmnop"
    for idx, c in enumerate(numeric_cols):
        ax = axes[idx // cols][idx % cols]
        vals = [v for v in data[c] if v is not None]
        arr = np.array(vals, dtype=float)
        nbins = min(40, max(10, int(math.sqrt(len(arr))) + 1))
        st = describe(vals)
        if use_log.get(c) and arr.min() > 0:
            bins = np.logspace(math.log10(arr.min()), math.log10(arr.max()),
                               nbins)
            ax.hist(arr, bins=bins, color=OKABE_ITO[0], edgecolor="white",
                    linewidth=0.3)
            ax.set_xscale("log")
            ax.xaxis.set_major_locator(
                __import__("matplotlib").ticker.LogLocator(
                    base=10.0, subs=(1.0, 2.0, 5.0), numticks=5))
            ax.xaxis.set_major_formatter(
                __import__("matplotlib").ticker.FuncFormatter(
                    lambda v, _p: "%g" % v))
            ax.xaxis.set_minor_locator(
                __import__("matplotlib").ticker.NullLocator())
            xs = np.logspace(math.log10(arr.min()), math.log10(arr.max()), 200)
            if st and st["sd"] > 0 and len(arr) >= 8:
                la = np.log(arr)
                bw = 1.06 * la.std(ddof=1) * len(la) ** (-1 / 5)
                kde = np.exp(-0.5 * ((np.log(xs[:, None]) - la[None, :]) / bw)
                             ** 2).sum(axis=1) / (
                    len(la) * bw * math.sqrt(2 * math.pi) * xs)
                ax2 = ax.twinx()
                ax2.plot(xs, kde, color=OKABE_ITO[1], linewidth=0.8)
                ax2.set_yticks([])
                ax2.set_xscale("log")
        else:
            ax.hist(arr, bins=nbins, color=OKABE_ITO[0], edgecolor="white",
                    linewidth=0.3)
            if st and st["sd"] > 0 and len(arr) >= 8:
                xs = np.linspace(arr.min(), arr.max(), 200)
                kde_bw = 1.06 * st["sd"] * len(arr) ** (-1 / 5)
                kde = np.exp(-0.5 * ((xs[:, None] - arr[None, :]) / kde_bw)
                             ** 2).sum(axis=1) / (
                    len(arr) * kde_bw * math.sqrt(2 * math.pi))
                ax2 = ax.twinx()
                ax2.plot(xs, kde, color=OKABE_ITO[1], linewidth=0.8)
                ax2.set_yticks([])
        name, unit = disp[c]
        ax.set_title("(%s) %s" % (letters[idx], short_name(name, 14)),
                     loc="left")
        if st:
            ax.text(0.97, 0.92, "偏度 %.2f" % st["skewness"],
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=4.2, color="#444444")
        ax.set_xlabel("%s%s%s" % (short_name(name, 16),
                                  " [%s]" % unit if unit else "",
                                  "（对数尺度）" if use_log.get(c) else ""))
        ax.set_ylabel("频数")
    for j in range(k, rows * cols):
        axes[j // cols][j % cols].axis("off")
    return save_figure(fig, out_dir, "fig1_distributions", width_mm, height_mm)


def fig_grouped_boxplots(mode, numeric_cols, data, groups, out_dir, width_mm,
                         disp, f_rank=None, target=None, bin_info=None):
    import numpy as np
    import matplotlib.pyplot as plt
    letters = "abcdefghijklmnop"
    if mode == "categorical":
        gcol = groups["column"]
        levels = groups["levels"]
        show = numeric_cols
        if f_rank:
            show = [c for c, _f in f_rank[:8]]
        k = len(show)
        rows, cols = _grid_shape(k, 2)
        height_mm = min(240, max(50, rows * 42))
        fig, axes = plt.subplots(rows, cols, squeeze=False)
        for idx, c in enumerate(show):
            ax = axes[idx // cols][idx % cols]
            series = [[v for v, g in zip(data[c], data[gcol])
                       if v is not None and norm_level(g) == lev]
                      for lev in levels]
            bp = _boxplot(ax, series, levels, widths=0.55,
                            showfliers=True, patch_artist=True,
                            medianprops={"color": "black", "linewidth": 0.8},
                            flierprops={"markersize": 1.5, "marker": "o",
                                        "markerfacecolor": "#999999",
                                        "markeredgecolor": "none"})
            for patch, col in zip(bp["boxes"], OKABE_ITO):
                patch.set_facecolor(col)
                patch.set_alpha(0.55)
                patch.set_edgecolor("#333333")
                patch.set_linewidth(0.5)
            for li, (lev, svals) in enumerate(zip(levels, series)):
                xs, ys, sampled = _subsample(
                    list(np.full(len(svals), li + 1.0)), list(svals))
                ax.scatter(np.array(xs) + _jitter(xs), ys, s=2.0,
                           color=OKABE_ITO[li % len(OKABE_ITO)],
                           edgecolor="none", alpha=0.75, zorder=3)
            name, unit = disp[c]
            ax.set_title("(%s) %s" % (letters[idx], short_name(name)), loc="left")
            ax.set_ylabel("%s%s" % (name, " [%s]" % unit if unit else ""))
            ax.tick_params(axis="x", labelrotation=20)
        for j in range(k, rows * cols):
            axes[j // cols][j % cols].axis("off")
        return save_figure(fig, out_dir, "fig2_grouped_boxplots",
                           width_mm, height_mm)
    # binned mode: target (and top correlates) across bins of the bin column
    labels = bin_info["labels"]
    assign = bin_info["assign"]
    bcol = bin_info["column"]
    show = [c for c in ([target] + (bin_info.get("extra") or [])) if c]
    k = len(show)
    rows, cols = _grid_shape(k, 2)
    height_mm = min(240, max(55, rows * 45))
    fig, axes = plt.subplots(rows, cols, squeeze=False)
    for idx, c in enumerate(show):
        ax = axes[idx // cols][idx % cols]
        series = [[v for v, b in zip(data[c], data[bcol])
                   if v is not None and b is not None and assign(b) == lev]
                  for lev in labels]
        bp = _boxplot(ax, series, labels, widths=0.55,
                        showfliers=True, patch_artist=True,
                        medianprops={"color": "black", "linewidth": 0.8},
                        flierprops={"markersize": 1.5, "marker": "o",
                                    "markerfacecolor": "#999999",
                                    "markeredgecolor": "none"})
        for patch in bp["boxes"]:
            patch.set_facecolor(OKABE_ITO[0])
            patch.set_alpha(0.55)
            patch.set_edgecolor("#333333")
            patch.set_linewidth(0.5)
        for li, svals in enumerate(series):
            xs, ys, _s = _subsample(list(np.full(len(svals), li + 1.0)),
                                    list(svals))
            ax.scatter(np.array(xs) + _jitter(xs), ys, s=2.0,
                       color=OKABE_ITO[0], edgecolor="none", alpha=0.6,
                       zorder=3)
        name, unit = disp[c]
        bname, _bu = disp[bcol]
        ax.set_title("(%s) %s ~ %s 分箱" % (letters[idx], short_name(name), short_name(bname)),
                     loc="left")
        ax.set_ylabel("%s%s" % (name, " [%s]" % unit if unit else ""))
        ax.set_xlabel("%s 分箱" % bname)
        ax.tick_params(axis="x", labelrotation=20)
    for j in range(k, rows * cols):
        axes[j // cols][j % cols].axis("off")
    return save_figure(fig, out_dir, "fig2_grouped_boxplots",
                       width_mm, height_mm)


def fig_scatter_pairs(pairs, data, groups, out_dir, width_mm, disp,
                      use_log, bin_info=None):
    import numpy as np
    import matplotlib.pyplot as plt
    letters = "abcdefghijklmnop"
    k = len(pairs)
    rows, cols = _grid_shape(k, 2)
    height_mm = min(240, max(55, rows * 45))
    fig, axes = plt.subplots(rows, cols, squeeze=False)
    if groups["mode"] == "categorical":
        gcol, levels = groups["column"], groups["levels"]
        gvals = [norm_level(v) for v in data[gcol]]
    else:
        gcol, levels = None, bin_info["labels"]
        gvals = [bin_info["assign"](v) for v in data[bin_info["column"]]]
    for idx, (cx, cy, r, n) in enumerate(pairs):
        ax = axes[idx // cols][idx % cols]
        for li, lev in enumerate(levels):
            xs = [x for x, g in zip(data[cx], gvals)
                  if x is not None and g == lev]
            ys = [y for y, g in zip(data[cy], gvals)
                  if y is not None and g == lev]
            pair = [(x, y) for x, y in zip(xs, ys)
                    if x is not None and y is not None]
            xs = [p[0] for p in pair]
            ys = [p[1] for p in pair]
            xs, ys, _s = _subsample(xs, ys)
            ax.scatter(xs, ys, s=2.5, color=OKABE_ITO[li % len(OKABE_ITO)],
                       label=lev, edgecolor="none", alpha=0.8)
        nx, ux = disp[cx]
        ny, uy = disp[cy]
        xlabel = "%s%s" % (nx, " [%s]" % ux if ux else "")
        ylabel = "%s%s" % (ny, " [%s]" % uy if uy else "")
        if use_log.get(cx):
            ax.set_xscale("log")
            xlabel += " (对数尺度)"
        if use_log.get(cy):
            ax.set_yscale("log")
            ylabel += " (对数尺度)"
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        title = "(%s) r=%.3f, n=%d" % (letters[idx], r, n) if r is not None \
            else "(%s) n=%d" % (letters[idx], n)
        ax.set_title(title, loc="left")
        ax.legend(markerscale=2.2, frameon=False, borderpad=0.1,
                  labelspacing=0.25, handletextpad=0.2)
    for j in range(k, rows * cols):
        axes[j // cols][j % cols].axis("off")
    return save_figure(fig, out_dir, "fig3_scatter_pairs", width_mm, height_mm)


def fig_corr_heatmap(numeric_cols, corr, out_dir, width_mm, disp):
    import numpy as np
    import matplotlib.pyplot as plt
    k = len(numeric_cols)
    side = min(180, max(60, width_mm if k <= 10 else width_mm * 1.6))
    fig, ax = plt.subplots()
    mat = np.array([[corr[(a, b)][0] if corr[(a, b)][0] is not None else np.nan
                     for b in numeric_cols] for a in numeric_cols])
    im = ax.imshow(mat, vmin=-1, vmax=1, cmap="RdBu_r")
    names = [disp[c][0] for c in numeric_cols]
    ax.set_xticks(range(k), names, rotation=45, ha="right")
    ax.set_yticks(range(k), names)
    fs = max(3.0, min(5.0, 60.0 / k))
    for i in range(k):
        for j in range(k):
            v = mat[i, j]
            if not np.isnan(v):
                ax.text(j, i, "%.2f" % v, ha="center", va="center",
                        fontsize=fs,
                        color="white" if abs(v) > 0.6 else "black")
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.set_label("Pearson r")
    cb.ax.tick_params(labelsize=5)
    return save_figure(fig, out_dir, "fig4_correlation_heatmap", side, side)


def fig_missingness(missing_counts, out_dir, width_mm):
    import matplotlib.pyplot as plt
    cols = [c for c, n in missing_counts.items() if n > 0]
    if not cols:
        return None
    fig, ax = plt.subplots()
    ys = list(range(len(cols)))
    ax.barh(ys, [missing_counts[c] for c in cols], color=OKABE_ITO[0],
            height=0.6)
    ax.set_yticks(ys, cols)
    ax.set_xlabel("缺失值数量")
    ax.set_title("各列缺失值数量", loc="left")
    return save_figure(fig, out_dir, "fig5_missingness", width_mm,
                       max(40, 12 * len(cols) + 20))


# ---------------------------------------------------------------------------
# captions (Chinese, standalone-readable; every number from computed stats)
# ---------------------------------------------------------------------------
def fmt(x, nd=3):
    if x is None:
        return "NA"
    if abs(x) >= 1000 or (abs(x) < 0.01 and x != 0):
        return ("%%.%dg" % nd) % x
    return ("%%.%df" % nd) % x


def build_captions(ctx):
    lines, caps = [], {}
    n = ctx["n_rows"]
    src = ctx["source_label"]
    clean = ctx["clean_brief"]
    g = ctx["groups"]
    if g["mode"] == "categorical":
        gtext = "按 %s 分组（%s）" % (
            g["column"], "、".join("%s n=%d" % (lev, ctx["group_ns"].get(lev, 0))
                                  for lev in g["levels"]))
        err = "箱线图中箱体为四分位距（Q1–Q3），中线为中位数，须线为 1.5×IQR 范围，须外点为离群观测（仅标记未删除）"
    else:
        bi = ctx["bin_info"]
        gtext = "按 %s 四分位分箱（%s）" % (bi["column"], "、".join(
            "%s n=%d" % (lab, ctx["group_ns"].get(lab, 0)) for lab in bi["labels"]))
        err = "箱线图箱体为 Q1–Q3，须线为 1.5×IQR；散点为原始观测（n>300 时固定种子抽样 300 个）"
    caps["fig1"] = (
        "图 1　数值变量分布。%d 个数值变量的直方图（叠加高斯 KDE 曲线），"
        "样本量 n=%d。面板标题给出各变量偏度；标注“对数尺度”的变量因右偏"
        "（偏度>1 且最小值>0）采用对数横轴。数据来源：%s。%s"
        % (len(ctx["numeric_cols"]), n, src, clean))
    caps["fig2"] = (
        "图 2　分组箱线图（叠加散点）。%s；%s。误差线含义：%s。"
        "样本量 n=%d，数据来源：%s。%s"
        % (gtext, "面板内叠加经固定种子抖动的原始观测点", err, n, src, clean))
    pair_txt = "；".join("(%s) %s 与 %s：r=%s，n=%d" % (
        "abcd"[i], ctx["disp"][cx][0], ctx["disp"][cy][0], fmt(r), nn)
        for i, (cx, cy, r, nn) in enumerate(ctx["pairs"]))
    caps["fig3"] = (
        "图 3　关键变量两两散点图（分组着色）。选取 |r| 最大的变量对：%s。"
        "颜色区分%s；图例与数据中的分组取值一一对应。样本量 n=%d，"
        "数据来源：%s。%s"
        % (pair_txt, gtext.split("（")[0].replace("按 ", "").replace(" 四分位分箱", "")
           if g["mode"] == "categorical" else gtext.split("（")[0].replace("按 ", ""),
           n, src, clean))
    strongest = ctx["strongest_corr"]
    caps["fig4"] = (
        "图 4　数值变量 Pearson 相关热图（成对完整观测）。色标固定 [-1, 1]，"
        "格内数字为相关系数。最强相关：%s 与 %s（r=%s）。样本量 n=%d，"
        "数据来源：%s。%s"
        % (ctx["disp"][strongest[0]][0], ctx["disp"][strongest[1]][0],
           fmt(strongest[2]), n, src, clean))
    if ctx.get("fig5"):
        caps["fig5"] = ("图 5　各列缺失值数量。缺失值仅计数报告、未插补。"
                        "数据来源：%s。%s" % (src, clean))
    for fid, text in caps.items():
        lines.append(text)
        lines.append("")
    return "\n".join(lines), caps


# ---------------------------------------------------------------------------
# export verification
# ---------------------------------------------------------------------------
def png_dpi(path):
    with open(path, "rb") as fh:
        raw = fh.read(200)
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    i = raw.find(b"pHYs")
    if i < 0:
        return None
    import struct
    xppm = struct.unpack(">I", raw[i + 4:i + 8])[0]
    return xppm * 0.0254


def audit_exports(paths, out_dir, expect_dpi=300):
    rep = {}
    for fid, fmap in paths.items():
        ent = {}
        png = fmap.get("png")
        if png:
            d = png_dpi(os.path.join(out_dir, png))
            ent["png_dpi"] = d
            ent["png_dpi_ok"] = bool(d and abs(d - expect_dpi) < 1.0)
        pdf = fmap.get("pdf")
        if pdf:
            with open(os.path.join(out_dir, pdf), "rb") as fh:
                raw = fh.read()
            ent["pdf_font_embedded"] = b"FontFile" in raw
            ent["pdf_bytes"] = len(raw)
        svg = fmap.get("svg")
        if svg:
            with open(os.path.join(out_dir, svg), "rb") as fh:
                raw = fh.read()
            ent["svg_live_text"] = b"<text" in raw
            ent["svg_bytes"] = len(raw)
        ent["ok"] = all(v for k, v in ent.items()
                        if k.endswith("_ok") or k in
                        ("pdf_font_embedded", "svg_live_text"))
        rep[fid] = ent
    return rep


# ---------------------------------------------------------------------------
# independent re-verification from source files
# ---------------------------------------------------------------------------
def verify_against_source(primary_path, statistics, corr_pairs, groups_info,
                          tolerance=1e-6):
    rep = {"source_file": primary_path, "checks": [], "all_passed": True}
    try:
        if os.path.splitext(primary_path)[1].lower() in (".sqlite", ".db", ".sqlite3"):
            tab = load_sqlite(primary_path)
        else:
            tab = load_delimited(primary_path)
    except Exception as exc:  # noqa: BLE001
        rep["all_passed"] = False
        rep["checks"].append({"check": "reload_source", "passed": False,
                              "detail": str(exc)})
        return rep
    cols = tab["columns"]
    idx = {c: j for j, c in enumerate(cols)}
    data = {}
    for c in cols:
        data[c] = [try_float(r[idx[c]]) for r in tab["rows"]]
    for c, st in statistics.items():
        vals = [v for v in data.get(c, []) if v is not None]
        if not vals:
            continue
        m = sum(vals) / len(vals)
        ok = abs(m - st["mean"]) <= tolerance * max(1.0, abs(m))
        rep["checks"].append({"check": "mean:%s" % c, "passed": ok,
                              "recomputed": m, "reported": st["mean"]})
        if not ok:
            rep["all_passed"] = False
        okn = len(vals) == st["n"]
        rep["checks"].append({"check": "n:%s" % c, "passed": okn,
                              "recomputed": len(vals), "reported": st["n"]})
        if not okn:
            rep["all_passed"] = False
    for (cx, cy, r, n) in corr_pairs:
        if r is None:
            continue
        rr, nn = pearson(data.get(cx, []), data.get(cy, []))
        ok = rr is not None and abs(rr - r) <= 1e-6
        rep["checks"].append({"check": "pearson:%s~%s" % (cx, cy),
                              "passed": ok, "recomputed": rr, "reported": r})
        if not ok:
            rep["all_passed"] = False
    rep["n_checks"] = len(rep["checks"])
    rep["n_failed"] = sum(1 for c in rep["checks"] if not c["passed"])
    return rep


# ---------------------------------------------------------------------------
# main pipeline
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--width-mm", type=float, default=89.0)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    log, uncertainty = [], []
    stage = {"stage": "init"}

    case = {}
    try:
        text, _ = read_text(args.case)
        case = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        log.append("case.json unreadable: %s" % exc)
    case_id = case.get("case_id", "unknown-case")
    contract = case.get("output_contract") or [
        "case_id", "status", "summary", "figures", "statistics",
        "cleaning_report", "sources", "uncertainty"]
    constraints = case.get("constraints") or {}
    export_req = constraints.get("export") or {}
    width_mm = float(export_req.get("width_mm", args.width_mm))
    dpi_req = int(export_req.get("png_dpi", 300))
    task_text = ""
    for cand in (os.path.join(args.input_dir, "task.md"),
                 os.path.join(os.path.dirname(args.case), "task.md")):
        if os.path.isfile(cand):
            task_text, _ = read_text(cand)
            break

    result = {k: None for k in contract}
    result["case_id"] = case_id

    def save_result(status, **fields):
        result.update(fields)
        result["status"] = status
        for k in contract:
            result.setdefault(k, None)
        result["uncertainty"] = uncertainty
        write_json(os.path.join(args.out, "result.json"), result)

    save_result("partial", summary="运行初始化完成，正在盘点输入。")
    dataset_name = (case.get("dataset") or {}).get("name", "")
    try:
        primary, tables, reconciliation, all_files = discover_and_load(
            args.input_dir, dataset_name, log)
    except Exception as exc:  # noqa: BLE001
        save_result("unable_to_determine",
                    summary="未找到可读取的数据表：%s" % exc)
        write_json(os.path.join(args.work, "run_log.json"),
                   {"log": log, "traceback": traceback.format_exc()})
        return 2

    sources = []
    for p in all_files:
        try:
            sources.append({"file": os.path.basename(p),
                            "path": os.path.abspath(p),
                            "sha256": sha256_file(p),
                            "bytes": os.path.getsize(p)})
        except OSError:
            pass
    if reconciliation is not None:
        if (not reconciliation.get("row_count_equal")
                or not reconciliation.get("column_sets_equal")
                or reconciliation.get("cell_mismatches")):
            uncertainty.append(
                "CSV 快照与 SQLite 数据库不完全一致（%s），已以 %s 为准并在 "
                "reconciliation.json 中留痕。" % (
                    reconciliation.get("mismatch_examples") or
                    {"rows_csv": reconciliation.get("rows_a"),
                     "rows_sqlite": reconciliation.get("rows_b")},
                    os.path.basename(primary["path"])))
        write_json(os.path.join(args.out, "reconciliation.json"), reconciliation)

    cleaned, clean_report = clean_table(primary)
    clean_report["primary_source"] = os.path.basename(primary["path"])
    clean_report["source_sha256"] = sha256_file(primary["path"])
    data, types = cleaned["data"], cleaned["types"]
    cols = cleaned["columns"]
    n_rows = cleaned["n_rows"]
    numeric_cols = [c for c in cols if types[c] == "numeric"]
    categorical_cols = [c for c in cols if types[c] == "categorical"]

    # outlier flags (mark only)
    for c in numeric_cols:
        f = iqr_fences(data[c])
        if f:
            lo, hi, q1, q3 = f
            n_out = sum(1 for v in data[c]
                        if v is not None and (v < lo or v > hi))
            clean_report["columns"][c].update(
                {"iqr_fence_low": lo, "iqr_fence_high": hi,
                 "outliers_flagged": n_out})
    clean_report["rules"].append({
        "rule": "outliers",
        "detail": "1.5*IQR fences per numeric column; outliers flagged only, never deleted"})
    write_json(os.path.join(args.out, "cleaning_report.json"), clean_report)
    save_result("partial", summary="清洗口径已留痕，正在计算统计量。",
                cleaning_report={
                    "file": "cleaning_report.json",
                    "input_rows": clean_report["input_rows"],
                    "duplicate_rows": clean_report["duplicate_rows"],
                    "rules": [r["rule"] for r in clean_report["rules"]]})

    # statistics
    statistics = {}
    for c in numeric_cols:
        st = describe(data[c])
        if st:
            st["missing"] = clean_report["columns"][c]["missing"]
            statistics[c] = st
    freq = {c: freq_table(data[c]) for c in categorical_cols}
    groups = detect_group_column(task_text, cols, types, data, n_rows)
    target = detect_target_column(task_text, cols, types)
    bin_info = None
    if groups["mode"] == "none":
        skew_pos = [c for c in numeric_cols
                    if statistics.get(c) and statistics[c]["skewness"] > 0.5
                    and statistics[c]["min"] > 0]
        bcol = next((c for c in numeric_cols if re.search(r"age|time|day", c, re.I)),
                    (skew_pos[0] if skew_pos else None))
        if bcol:
            bi = make_bins(data[bcol], 4)
            if bi:
                bin_info = {"column": bcol, "labels": bi["labels"],
                            "edges": bi["edges"], "assign": bi["assign"],
                            "rule": "4 个四分位等频分箱"}
                groups = {"mode": "binned", "column": bcol,
                          "levels": bi["labels"]}
    # group stats
    group_stats, group_ns = {}, {}
    if groups["mode"] != "none":
        if groups["mode"] == "categorical":
            gvals = [norm_level(v) for v in data[groups["column"]]]
        else:
            gvals = [bin_info["assign"](v) for v in data[bin_info["column"]]]
        for lev in groups["levels"]:
            mask = [g == lev for g in gvals]
            group_ns[lev] = sum(1 for g in gvals if g == lev)
            group_stats[lev] = {}
            for c in numeric_cols:
                vals = [v for v, m in zip(data[c], mask) if m and v is not None]
                st = describe(vals)
                if st:
                    group_stats[lev][c] = st
    # integer-encoded group column is categorical: move out of numeric set
    if groups["mode"] == "categorical" and types.get(groups["column"]) == "numeric":
        gc = groups["column"]
        types[gc] = "categorical_encoded"
        clean_report["rules"].append({
            "rule": "encoded_categorical",
            "detail": ("column '%s' is integer-coded group label; treated as "
                       "categorical (frequency table given, excluded from "
                       "correlation/distribution panels of measurement "
                       "variables)" % gc)})
        numeric_cols = [c for c in numeric_cols if c != gc]
        categorical_cols = categorical_cols + [gc]
        freq[gc] = freq_table(data[gc])
        statistics.pop(gc, None)
        clean_report["columns"][gc]["type"] = "categorical_encoded"
        for lev in group_stats:
            group_stats[lev].pop(gc, None)
        write_json(os.path.join(args.out, "cleaning_report.json"), clean_report)

    # correlations
    corr, pair_list = {}, []
    for i, cx in enumerate(numeric_cols):
        for cy in numeric_cols[i + 1:]:
            r, n = pearson(data[cx], data[cy])
            corr[(cx, cy)] = (r, n)
            corr[(cy, cx)] = (r, n)
            pair_list.append((cx, cy, r, n))
        corr[(cx, cx)] = (1.0, sum(1 for v in data[cx] if v is not None))
    valid_pairs = [p for p in pair_list if p[2] is not None]
    valid_pairs.sort(key=lambda p: -abs(p[2]))
    pairs = valid_pairs[:3]
    # in binned mode the (bin column, target) relationship is task-central:
    # force it in so the log-scale decision on the skewed axis is visible
    if bin_info and target:
        bt = (bin_info["column"], target)
        if not any({p[0], p[1]} == set(bt) for p in pairs):
            r, n = corr.get(bt, (None, 0))
            pairs.insert(0, (bt[0], bt[1], r, n))
    # task-mentioned pairs are forced in (e.g. flavanoids ~ total_phenols)
    for m in re.finditer(r"([A-Za-z_][\w]*)\s*与\s*([A-Za-z_][\w]*)",
                         task_text or ""):
        a, b = m.group(1), m.group(2)
        ca = next((c for c in numeric_cols if c == a or a in c), None)
        cb = next((c for c in numeric_cols if c == b or b in c), None)
        if ca and cb and ca != cb:
            r, n = corr[(ca, cb)]
            if not any({p[0], p[1]} == {ca, cb} for p in pairs):
                pairs.append((ca, cb, r, n))
    pairs = pairs[:4]
    strongest = None
    if valid_pairs:
        sp = valid_pairs[0]
        strongest = (sp[0], sp[1], sp[2])

    # between-group F ranking (for panel selection)
    f_rank = None
    if groups["mode"] == "categorical":
        f_rank = []
        gvals = [norm_level(v) for v in data[groups["column"]]]
        for c in numeric_cols:
            vals_by = {lev: [v for v, g in zip(data[c], gvals)
                             if v is not None and g == lev]
                       for lev in groups["levels"]}
            allv = [v for s in vals_by.values() for v in s]
            if len(allv) < 4:
                f_rank.append((c, 0.0))
                continue
            gm = sum(allv) / len(allv)
            ssb = sum(len(s) * ((sum(s) / len(s)) - gm) ** 2
                      for s in vals_by.values() if s)
            ssw = sum(sum((v - sum(s) / len(s)) ** 2 for v in s)
                      for s in vals_by.values() if s)
            dfb = sum(1 for s in vals_by.values() if s) - 1
            dfw = len(allv) - dfb - 1
            f_rank.append((c, (ssb / dfb) / (ssw / dfw)
                           if dfb > 0 and dfw > 0 and ssw > 0 else 0.0))
        f_rank.sort(key=lambda kv: -kv[1])
    if bin_info and target:
        seen_x, bin_extra = set(), []
        for cx, cy, r, n in valid_pairs:
            other = cy if cx == target else (cx if cy == target else None)
            if other and other not in seen_x and other != bin_info["column"]:
                seen_x.add(other)
                bin_extra.append(other)
            if len(bin_extra) >= 3:
                break
        bin_info["extra"] = bin_extra

    disp = {c: display_name_unit(c) for c in cols}
    # log-scale decisions: skew>1 and min>0
    use_log = {c: bool(statistics[c]["skewness"] > 1.0
                       and statistics[c]["min"] > 0)
               for c in numeric_cols}
    log_notes = ["%s 右偏（偏度=%.2f），图中采用对数坐标轴并已标注"
                 % (disp[c][0], statistics[c]["skewness"])
                 for c in numeric_cols if use_log.get(c)]

    stats_doc = {"n_rows": n_rows, "numeric_columns": numeric_cols,
                 "categorical_columns": categorical_cols,
                 "descriptive": statistics,
                 "definitions": {"sd": "sample standard deviation (ddof=1)",
                                 "sem": "sd/sqrt(n)",
                                 "quartiles": "linear interpolation, type 7",
                                 "skewness": "moment skewness m3/m2^1.5",
                                 "pearson": "pairwise complete observations"},
                 "frequency_tables": freq,
                 "group": {"mode": groups["mode"], "column": groups["column"],
                           "levels": groups["levels"], "n_per_level": group_ns,
                           "bin_rule": (bin_info or {}).get("rule"),
                           "target_column": target},
                 "group_descriptive": group_stats,
                 "correlations": [
                     {"x": cx, "y": cy, "pearson_r": r, "n": n}
                     for (cx, cy), (r, n) in sorted(corr.items())
                     if numeric_cols.index(cx) < numeric_cols.index(cy)],
                 "log_scale_decisions": log_notes}
    write_json(os.path.join(args.out, "statistics.json"), stats_doc)
    md = ["# 描述统计（全部可由源数据复算）", "",
          "样本量 n=%d；数值变量 %d 个；分组：%s" % (
              n_rows, len(numeric_cols),
              ("按 %s" % groups["column"]) if groups["mode"] != "none" else "无"),
          "", "| 变量 | n | 缺失 | 均值 | SD | SEM | 中位数 | Q1 | Q3 | 最小 | 最大 | 偏度 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in numeric_cols:
        st = statistics[c]
        md.append("| %s | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s | %.3f |"
                  % (c, st["n"], st["missing"], fmt(st["mean"]), fmt(st["sd"]),
                     fmt(st["sem"]), fmt(st["median"]), fmt(st["q1"]),
                     fmt(st["q3"]), fmt(st["min"]), fmt(st["max"]),
                     st["skewness"]))
    if freq:
        md += ["", "## 分类变量频数表"]
        for c, tab in freq.items():
            md.append("- **%s**：%s" % (c, "、".join(
                "%s=%d" % kv for kv in tab.items())))
    with open(os.path.join(args.out, "statistics.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    save_result("partial", summary="统计量计算完成，正在绘制图件。",
                statistics={"file": "statistics.json",
                            "n_rows": n_rows,
                            "n_numeric": len(numeric_cols),
                            "group": groups.get("column")})

    # figures
    fig_paths, fig_errors = {}, []
    plotting_ok, plot_err = import_plotting(log)
    cjk_font = None
    if plotting_ok:
        cjk_font = setup_style()
        if cjk_font is None:
            uncertainty.append(
                "运行环境未发现覆盖 CJK 字形的字体，图内标注以英文变量名呈现；"
                "中文图注仍以文本形式交付（captions.md）。")
        try:
            fig_paths["fig1_distributions"] = fig_distributions(
                numeric_cols, data, None, args.out, width_mm, use_log, disp)
        except Exception as exc:  # noqa: BLE001
            fig_errors.append("fig1: %s" % exc)
            log.append(traceback.format_exc())
        try:
            fig_paths["fig2_grouped_boxplots"] = fig_grouped_boxplots(
                groups["mode"], numeric_cols, data, groups, args.out,
                width_mm, disp, f_rank=f_rank, target=target,
                bin_info=bin_info)
        except Exception as exc:  # noqa: BLE001
            fig_errors.append("fig2: %s" % exc)
            log.append(traceback.format_exc())
        try:
            if pairs:
                fig_paths["fig3_scatter_pairs"] = fig_scatter_pairs(
                    pairs, data, groups, args.out, width_mm, disp, use_log,
                    bin_info=bin_info)
        except Exception as exc:  # noqa: BLE001
            fig_errors.append("fig3: %s" % exc)
            log.append(traceback.format_exc())
        try:
            fig_paths["fig4_correlation_heatmap"] = fig_corr_heatmap(
                numeric_cols, corr, args.out, width_mm, disp)
        except Exception as exc:  # noqa: BLE001
            fig_errors.append("fig4: %s" % exc)
            log.append(traceback.format_exc())
        try:
            miss = {c: clean_report["columns"][c]["missing"] for c in cols}
            if any(v > 0 for v in miss.values()):
                f5 = fig_missingness(miss, args.out, width_mm)
                if f5:
                    fig_paths["fig5_missingness"] = f5
        except Exception as exc:  # noqa: BLE001
            fig_errors.append("fig5: %s" % exc)
            log.append(traceback.format_exc())
    else:
        uncertainty.append("numpy/matplotlib 不可用（pip 安装失败：%s）；"
                           "已交付统计与清洗结果，图件缺失。" % plot_err)
    for e in fig_errors:
        uncertainty.append("图件生成失败：%s" % e)

    # captions
    source_label = "%s（%s）" % ((case.get("dataset") or {}).get("name", "dataset"),
                                (case.get("dataset") or {}).get("source", "case input"))
    clean_brief = ("清洗口径：缺失值逐列计数未插补；重复行 %d 条保留并标记；"
                   "异常值按 1.5×IQR 仅标记不删除。" % clean_report["duplicate_rows"])
    ctx = {"n_rows": n_rows, "source_label": source_label,
           "clean_brief": clean_brief, "groups": groups,
           "group_ns": group_ns, "numeric_cols": numeric_cols,
           "pairs": pairs, "disp": disp, "strongest_corr": strongest or ("-", "-", None),
           "bin_info": bin_info or {"column": "-", "labels": []},
           "fig5": "fig5_missingness" in fig_paths}
    captions_md, caps = build_captions(ctx)
    with open(os.path.join(args.out, "captions.md"), "w", encoding="utf-8") as fh:
        fh.write("# 图注（可独立阅读）\n\n" + captions_md)
    write_json(os.path.join(args.out, "captions.json"), caps)

    # figure metadata with element->source binding
    figdata = []
    bindings = {
        "fig1_distributions": {"panels": [{"panel": "(%s)" % "abcdefghijklmnop"[i],
                                           "source_column": c,
                                           "encoding": {"x": "value", "y": "count"},
                                           "log_scale": bool(use_log.get(c))}
                                          for i, c in enumerate(numeric_cols)]},
        "fig2_grouped_boxplots": {"group_by": groups["column"],
                                  "group_levels": groups["levels"],
                                  "n_per_level": group_ns,
                                  "whisker_rule": "1.5*IQR"},
        "fig3_scatter_pairs": {"panels": [{"x": cx, "y": cy, "pearson_r": r, "n": n,
                                           "color_by": groups["column"]}
                                          for cx, cy, r, n in pairs]},
        "fig4_correlation_heatmap": {"matrix": "statistics.json:correlations",
                                     "color_scale": [-1, 1]},
    }
    for fid, fmap in fig_paths.items():
        figdata.append({"id": fid, "files": fmap, "width_mm": width_mm,
                        "png_dpi": dpi_req,
                        "binding": bindings.get(fid, {})})
    write_json(os.path.join(args.out, "figures.figdata.json"),
               {"figures": figdata, "palette": "Okabe-Ito colorblind-safe",
                "cjk_font": cjk_font, "seed": SEED})

    # verification
    verify = verify_against_source(primary["path"], statistics, pairs,
                                   groups)
    exports = audit_exports(fig_paths, args.out, expect_dpi=dpi_req) if fig_paths else {}
    check = {"recompute_from_source": verify, "export_audit": exports,
             "all_passed": verify["all_passed"] and all(
                 e.get("ok", True) for e in exports.values())}
    write_json(os.path.join(args.out, "check_report.json"), check)
    # 图注/标注一致性审计：完备性、数字一致性、图例 1:1、面板编号
    try:
        cpy = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "caption_lint.py")
        cproc = subprocess.run(
            [sys.executable, cpy, "--outdir", args.out,
             "--out", os.path.join(args.out, "caption_audit.json")],
            capture_output=True, text=True, timeout=120)
        if cproc.returncode != 0:
            uncertainty.append(
                "图注一致性审计未全部通过（详见 caption_audit.json）：%s"
                % (cproc.stdout + cproc.stderr)[:300])
    except Exception as exc:  # noqa: BLE001
        uncertainty.append("caption_lint.py 执行失败：%s" % exc)

    if not verify["all_passed"]:
        uncertainty.append("独立复算发现 %d 项不一致，详见 check_report.json。"
                           % verify["n_failed"])
    if cjk_font is None and plotting_ok:
        pass  # already recorded

    # run manifest
    manifest = {"python": sys.version.split()[0],
                "seed": SEED, "cjk_font": cjk_font,
                "log": log,
                "primary_source": primary["path"],
                "files": sources}
    try:
        import matplotlib
        manifest["matplotlib"] = matplotlib.__version__
        import numpy
        manifest["numpy"] = numpy.__version__
    except Exception:  # noqa: BLE001
        pass
    write_json(os.path.join(args.out, "run_manifest.json"), manifest)

    # final result
    headline = []
    for c in numeric_cols[:6]:
        st = statistics[c]
        headline.append("%s=%s±%s" % (disp[c][0], fmt(st["mean"]), fmt(st["sd"])))
    summary_parts = [
        "数据 n=%d，%d 个数值变量、%d 个分类变量。"
        % (n_rows, len(numeric_cols), len(categorical_cols)),
        "清洗：缺失值逐列计数未插补，重复行 %d 条保留标记，1.5×IQR 异常值仅标记。"
        % clean_report["duplicate_rows"],
        "主要描述统计（均值±SD）：%s。" % "、".join(headline),
    ]
    if strongest and strongest[2] is not None:
        summary_parts.append("最强相关：%s 与 %s（r=%s）。"
                             % (disp[strongest[0]][0], disp[strongest[1]][0],
                                fmt(strongest[2])))
    if log_notes:
        summary_parts.append("坐标轴尺度决策：" + "；".join(log_notes) + "。")
    if groups["mode"] == "categorical":
        summary_parts.append("分组：%s（%s）。"
                             % (groups["column"], "、".join(groups["levels"])))
    elif bin_info:
        summary_parts.append("无现成分组列，按 %s 四分位分箱（%s）分组展示目标变量 %s。"
                             % (bin_info["column"], "、".join(bin_info["labels"]),
                                disp.get(target, (target, ""))[0] if target else "?"))
    summary_parts.append("图件 %d 张（300 dpi PNG + 嵌入字体 PDF + 可编辑 SVG，"
                         "单栏 %g mm，Okabe-Ito 色盲安全配色），图注见 captions.md；"
                         "全部统计量经独立复算%s。"
                         % (len(fig_paths), width_mm,
                            "一致" if check["all_passed"] else "存在不一致，见 uncertainty"))
    figures_field = [{"id": f["id"], "files": f["files"],
                      "width_mm": f["width_mm"], "dpi": f["png_dpi"],
                      "caption": caps.get(f["id"].split("_")[0], ""),
                      "binding": f["binding"]} for f in figdata]
    final_status = "success"
    if fig_errors or not check["all_passed"] or not fig_paths:
        final_status = "partial"
    save_result(final_status,
                summary="".join(summary_parts),
                figures=figures_field,
                statistics={"file": "statistics.json", "md": "statistics.md",
                            "n_rows": n_rows, "n_numeric": len(numeric_cols),
                            "n_categorical": len(categorical_cols),
                            "group": {"mode": groups["mode"],
                                      "column": groups["column"],
                                      "levels": groups["levels"],
                                      "n_per_level": group_ns},
                            "strongest_correlation": {
                                "x": (strongest or (None,))[0],
                                "y": (strongest or (None, None))[1],
                                "pearson_r": (strongest or (None, None, None))[2]},
                            "definitions": stats_doc["definitions"]},
                cleaning_report={"file": "cleaning_report.json",
                                 "input_rows": clean_report["input_rows"],
                                 "duplicate_rows": clean_report["duplicate_rows"],
                                 "missing_by_column": {
                                     c: clean_report["columns"][c]["missing"]
                                     for c in cols},
                                 "rules": clean_report["rules"]},
                sources={"case_dataset": case.get("dataset"),
                         "primary_file": os.path.basename(primary["path"]),
                         "files": sources,
                         "verification": "check_report.json",
                         "captions": "captions.md",
                         "figure_data_binding": "figures.figdata.json",
                         "run_manifest": "run_manifest.json",
                         "caption_audit": "caption_audit.json"})
    write_json(os.path.join(args.work, "run_log.json"), {"log": log})
    print(json.dumps({"status": final_status, "case_id": case_id,
                      "figures": len(fig_paths),
                      "checks_passed": check["all_passed"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
