#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
figforge -- deterministic, data-dictionary-bound figure renderer with QC.

Core is Python 3.9+ standard library only. matplotlib is imported lazily
inside the `render` subcommand; when it is unavailable, figforge degrades
honestly: it still writes the validated plan echo, the figure_data CSVs and
figures_manifest.json (entries with status "figure_not_rendered"), records an
anomaly, and exits 3.

Exit codes:
  0  success
  1  qc found at least one FAILED check
  2  usage / validation error (bad plan, missing column, non-numeric column)
  3  render degraded because matplotlib is unavailable

No randomness is used anywhere in this file.
"""
import argparse
import csv
import hashlib
import json
import os
import sys

TOOL = "figforge"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FIG_TYPES = ("histogram", "scatter", "box", "bar")


class ForgeError(Exception):
    """Validation error; reported with [figforge] prefix, exit 2."""


# --------------------------------------------------------------------------- #
# small utilities
# --------------------------------------------------------------------------- #
def die(msg, code=2):
    print("[figforge] ERROR: %s" % msg, file=sys.stderr)
    sys.exit(code)


def info(msg):
    print("[figforge] %s" % msg)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_float(raw):
    """Return float(raw) or None for empty / non-numeric input."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt_num(v):
    """Full-precision, deterministic number formatting for CSV output."""
    return repr(v)


# --------------------------------------------------------------------------- #
# dictionary loading (JSON {"columns": {...}} or CSV name,label,unit)
# --------------------------------------------------------------------------- #
def load_dictionary(path):
    if not path:
        info("WARNING: no --dictionary given; every plotted column will be "
             "flagged unit_unknown.")
        return {}
    if not os.path.isfile(path):
        die("dictionary not found: %s" % path)
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict):
        cols = obj.get("columns", obj)
        if not isinstance(cols, dict):
            die("dictionary JSON must contain an object 'columns'.")
        out = {}
        for name, entry in cols.items():
            entry = entry if isinstance(entry, dict) else {}
            out[str(name)] = {
                "label": str(entry.get("label") or name),
                "unit": (str(entry["unit"]).strip()
                         if entry.get("unit") is not None else ""),
                "description": str(entry.get("description") or ""),
            }
        return out
    # fall back to CSV: name,label,unit[,description]
    out = {}
    rdr = csv.DictReader(text.splitlines())
    fields = [f.strip() for f in (rdr.fieldnames or [])]
    if "name" not in fields:
        die("dictionary is neither valid JSON nor a CSV with a 'name' column: "
            "%s" % path)
    for row in rdr:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        out[name] = {
            "label": (row.get("label") or name).strip() or name,
            "unit": (row.get("unit") or "").strip(),
            "description": (row.get("description") or "").strip(),
        }
    return out


# --------------------------------------------------------------------------- #
# CSV reading -- two intentionally different code paths (render vs qc)
# --------------------------------------------------------------------------- #
def read_table_render(path):
    """Render path: csv.DictReader -> (header, list of row dicts)."""
    if not os.path.isfile(path):
        die("CSV not found: %s" % path)
    with open(path, "r", newline="", encoding="utf-8-sig") as fh:
        rdr = csv.DictReader(fh)
        rows = list(rdr)
        header = list(rdr.fieldnames or [])
    if not header:
        die("CSV has no header row: %s" % path)
    return header, rows


def read_table_qc(path):
    """QC path (independent): csv.reader -> (header, list of row lists)."""
    if not os.path.isfile(path):
        die("CSV not found: %s" % path)
    with open(path, "r", newline="", encoding="utf-8-sig") as fh:
        rdr = csv.reader(fh)
        all_rows = [r for r in rdr if r]
    if not all_rows:
        die("CSV is empty: %s" % path)
    return all_rows[0], all_rows[1:]


def qc_column_values(header, rows, column):
    """QC-path column extraction by positional index."""
    if column not in header:
        raise ForgeError("qc: column '%s' not found in CSV header" % column)
    idx = header.index(column)
    out = []
    for r in rows:
        out.append(r[idx] if idx < len(r) else "")
    return out


# --------------------------------------------------------------------------- #
# statistics -- two independent implementations
# --------------------------------------------------------------------------- #
def stats_render(values):
    """Render-path stats via sorted()."""
    s = sorted(values)
    return {"n_plotted": len(s),
            "min": s[0] if s else None,
            "max": s[-1] if s else None}


def stats_qc(values):
    """QC-path stats via a manual scan (independent code path)."""
    n = 0
    lo = None
    hi = None
    for v in values:
        n += 1
        if lo is None or v < lo:
            lo = v
        if hi is None or v > hi:
            hi = v
    return n, lo, hi


# --------------------------------------------------------------------------- #
# axis binding to the data dictionary
# --------------------------------------------------------------------------- #
def bind_axis(column, dictionary, require_unit, anomalies, review):
    """Axis label = '<dictionary label> (<unit>)'. Never guess a unit:
    a missing dictionary entry or missing unit raises anomaly unit_unknown,
    uses the bare name/label, and flags the figure needs_review."""
    entry = dictionary.get(column)
    if entry is None:
        label, unit = column, None
        anomalies.append({"code": "unit_unknown", "column": column,
                          "reason": "column has no data-dictionary entry"})
        review.append("unit_unknown:%s" % column)
    else:
        label = entry.get("label") or column
        unit = (entry.get("unit") or "").strip() or None
        if unit is None and require_unit:
            anomalies.append({"code": "unit_unknown", "column": column,
                              "reason": "dictionary entry defines no unit"})
            review.append("unit_unknown:%s" % column)
    text = "%s (%s)" % (label, unit) if unit else label
    return {"column": column, "label": label, "unit": unit, "axis_text": text}


def ensure_numeric(column, rows, fid):
    """Type-compatibility check: a numeric role needs >=1 parseable value."""
    for r in rows:
        if parse_float(r.get(column)) is not None:
            return
    raise ForgeError(
        "figure %s: column '%s' has no numeric values; "
        "type incompatible with a numeric axis" % (fid, column))


# --------------------------------------------------------------------------- #
# plan handling
# --------------------------------------------------------------------------- #
def load_plan(path):
    if not os.path.isfile(path):
        die("plan not found: %s" % path)
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            plan = json.load(fh)
    except json.JSONDecodeError as exc:
        die("plan is not valid JSON: %s (%s)" % (path, exc))
    if not isinstance(plan, dict) or not isinstance(plan.get("figures"), list):
        die("plan must be a JSON object with a 'figures' list.")
    seen = set()
    for spec in plan["figures"]:
        if not isinstance(spec, dict):
            die("each figure spec must be an object.")
        fid = spec.get("id")
        if not fid or not isinstance(fid, str):
            die("each figure spec needs a non-empty string 'id'.")
        if fid in seen:
            die("duplicate figure id in plan: %s" % fid)
        seen.add(fid)
        if spec.get("type") not in FIG_TYPES:
            die("figure %s: unknown type '%s' (allowed: %s)"
                % (fid, spec.get("type"), ", ".join(FIG_TYPES)))
    return plan


def build_plot_data(spec, header, rows, dictionary):
    """Validate one figure spec against the CSV and extract plotted values.

    Returns (data_columns, data_rows, axes, groups, dropped, anomalies,
             review). Raises ForgeError on any validation failure; the plan
    is never modified, only validated.
    """
    fid = spec["id"]
    ftype = spec["type"]
    anomalies, review = [], []

    def need(field):
        col = spec.get(field)
        if not col or not isinstance(col, str):
            raise ForgeError("figure %s: type '%s' requires field '%s'"
                             % (fid, ftype, field))
        if col not in header:
            raise ForgeError("figure %s: column '%s' not found in CSV header"
                             % (fid, col))
        return col

    groups = None
    if ftype == "histogram":
        xc = need("x")
        ensure_numeric(xc, rows, fid)
        vals, dropped = [], 0
        for r in rows:
            v = parse_float(r.get(xc))
            if v is None:
                dropped += 1
            else:
                vals.append(v)
        ax = bind_axis(xc, dictionary, True, anomalies, review)
        ax.update(stats_render(vals))
        ax["dropped"] = dropped
        axes = {"x": ax,
                "y": {"column": None, "label": "count", "unit": None,
                      "axis_text": "count", "n_plotted": None,
                      "min": None, "max": None}}
        data_columns, data_rows = [xc], [[fmt_num(v)] for v in vals]

    elif ftype == "scatter":
        xc, yc = need("x"), need("y")
        ensure_numeric(xc, rows, fid)
        ensure_numeric(yc, rows, fid)
        pairs, dropped = [], 0
        for r in rows:
            vx, vy = parse_float(r.get(xc)), parse_float(r.get(yc))
            if vx is None or vy is None:
                dropped += 1
            else:
                pairs.append((vx, vy))
        ax = bind_axis(xc, dictionary, True, anomalies, review)
        ax.update(stats_render([p[0] for p in pairs]))
        ax["dropped"] = dropped
        ay = bind_axis(yc, dictionary, True, anomalies, review)
        ay.update(stats_render([p[1] for p in pairs]))
        ay["dropped"] = dropped
        axes = {"x": ax, "y": ay}
        data_columns = [xc, yc]
        data_rows = [[fmt_num(p[0]), fmt_num(p[1])] for p in pairs]

    else:  # box or bar: numeric y grouped by a categorical column
        yc, gc = need("y"), need("group")
        ensure_numeric(yc, rows, fid)
        triples, dropped = [], 0
        raw_levels = set()
        for r in rows:
            g = (r.get(gc) or "").strip()
            if g:
                raw_levels.add(g)
            v = parse_float(r.get(yc))
            if not g or v is None:
                dropped += 1
            else:
                triples.append((g, v))
        levels = sorted({g for g, _ in triples})
        if not levels:
            raise ForgeError("figure %s: group column '%s' yields no "
                             "plottable (group, value) pairs" % (fid, gc))
        per_level = {lv: [] for lv in levels}
        counts = {}
        for g, v in triples:
            per_level[g].append(v)
        for lv in levels:
            counts[lv] = len(per_level[lv])
        for missing in sorted(raw_levels - set(levels)):
            anomalies.append({"code": "empty_group", "column": gc,
                              "level": missing,
                              "reason": "group level has zero numeric values"})
            review.append("empty_group:%s=%s" % (gc, missing))
        ay = bind_axis(yc, dictionary, True, anomalies, review)
        ay.update(stats_render([v for _, v in triples]))
        ay["dropped"] = dropped
        ax = bind_axis(gc, dictionary, False, anomalies, review)
        ax.update({"n_plotted": None, "min": None, "max": None})
        axes = {"x": ax, "y": ay}
        groups = {"column": gc, "levels": levels, "counts": counts}
        data_columns = [gc, yc]
        data_rows = [[g, fmt_num(v)] for g, v in triples]

    return data_columns, data_rows, axes, groups, dropped, anomalies, review


# --------------------------------------------------------------------------- #
# matplotlib (lazy) rendering
# --------------------------------------------------------------------------- #
def import_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return matplotlib, plt
    except Exception as exc:  # honest degradation path
        info("WARNING: matplotlib unavailable (%s); figures will not be "
             "rendered." % exc)
        return None, None


CJK_FONT_PREFERENCE = ("PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei",
                       "SimHei", "Heiti SC", "Songti SC")


def pick_cjk_font():
    """Deterministically pick the first available CJK font from a fixed
    preference list (depends only on installed fonts, no randomness).
    Returns None when no CJK font is installed."""
    try:
        from matplotlib import font_manager
        from matplotlib.font_manager import FontProperties
        for name in CJK_FONT_PREFERENCE:
            try:
                font_manager.findfont(FontProperties(family=name),
                                      fallback_to_default=False)
                return name
            except Exception:
                continue
    except Exception:
        pass
    return None


def set_deterministic_rcparams():
    from matplotlib import rcParams
    # DejaVu Sans-anchored fallback chain; when a CJK font is installed it is
    # placed first so CJK labels actually render (font fallback past the
    # first family is unreliable in some Agg builds). Deterministic: the
    # choice depends only on the fixed preference list and installed fonts.
    chain = ["DejaVu Sans", "PingFang SC", "Noto Sans CJK SC",
             "Microsoft YaHei", "SimHei", "Arial", "Liberation Sans",
             "sans-serif"]
    cjk = pick_cjk_font()
    if cjk:
        chain = [cjk] + [f for f in chain if f != cjk]
    rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "figure.figsize": (6.0, 4.2),
        "savefig.bbox": "tight",
        "font.family": "sans-serif",
        "font.sans-serif": chain,
        "font.size": 10.0,
        "axes.titlesize": 11.0,
        "axes.labelsize": 10.0,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.unicode_minus": False,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
        "lines.linewidth": 1.2,
        "xtick.labelsize": 9.0,
        "ytick.labelsize": 9.0,
        "legend.framealpha": 0.9,
    })


def draw_figure(plt, spec, axes, groups, data_columns, data_rows):
    """Draw one figure deterministically. No jitter, no RNG."""
    ftype = spec["type"]
    fid = spec["id"]
    fig, ax = plt.subplots()
    if ftype == "histogram":
        vals = [float(r[0]) for r in data_rows]
        n = len(vals)
        bins = max(5, min(20, int(n ** 0.5) + 1))  # deterministic given data
        ax.hist(vals, bins=bins, edgecolor="black", linewidth=0.5)
        ax.set_xlabel(axes["x"]["axis_text"])
        ax.set_ylabel("count")
    elif ftype == "scatter":
        xs = [float(r[0]) for r in data_rows]
        ys = [float(r[1]) for r in data_rows]
        ax.scatter(xs, ys, s=20, alpha=0.85, edgecolors="none")
        ax.set_xlabel(axes["x"]["axis_text"])
        ax.set_ylabel(axes["y"]["axis_text"])
    elif ftype == "box":
        levels = groups["levels"]
        per = {lv: [] for lv in levels}
        for g, v in data_rows:
            per[g].append(float(v))
        try:
            ax.boxplot([per[lv] for lv in levels], tick_labels=levels,
                       showmeans=True)
        except TypeError:  # matplotlib < 3.9 used 'labels'
            ax.boxplot([per[lv] for lv in levels], labels=levels,
                       showmeans=True)
        ax.set_xlabel(axes["x"]["axis_text"])
        ax.set_ylabel(axes["y"]["axis_text"])
    else:  # bar: group means +/- std, n annotated
        levels = groups["levels"]
        per = {lv: [] for lv in levels}
        for g, v in data_rows:
            per[g].append(float(v))
        means, stds, ns = [], [], []
        for lv in levels:
            vs = per[lv]
            m = sum(vs) / len(vs)
            var = sum((v - m) ** 2 for v in vs) / (len(vs) - 1) if len(vs) > 1 \
                else 0.0
            means.append(m)
            stds.append(var ** 0.5)
            ns.append(len(vs))
        pos = list(range(len(levels)))
        ax.bar(pos, means, yerr=stds, capsize=4, edgecolor="black",
               linewidth=0.5)
        for i, (m, s, c) in enumerate(zip(means, stds, ns)):
            ax.text(i, m + s, "n=%d" % c, ha="center", va="bottom",
                    fontsize=8)
        ax.set_xticks(pos)
        ax.set_xticklabels(levels)
        ax.set_xlabel(axes["x"]["axis_text"])
        ax.set_ylabel(axes["y"]["axis_text"])
    title = spec.get("title")
    if title:  # titles come from the plan only
        ax.set_title(str(title))
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- #
# figure_data CSV (exact plotted values + dropped-null note)
# --------------------------------------------------------------------------- #
def write_figure_data(path, fid, data_columns, data_rows, dropped, csv_sha):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write("# figforge figure_data id=%s dropped_null_rows=%d "
                 "source_csv_sha256=%s\n" % (fid, dropped, csv_sha))
        w = csv.writer(fh)
        w.writerow(data_columns)
        for row in data_rows:
            w.writerow(row)


def count_figure_data_rows(path):
    """QC-path row counter: non-comment data rows only."""
    n = 0
    with open(path, "r", newline="", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if line.startswith("#"):
                continue
            if i > 0 and not line.startswith("#") and n == 0 and \
                    line.strip() == "":
                continue
            n += 1
    return n - 1 if n > 0 else 0  # subtract header


# --------------------------------------------------------------------------- #
# subcommand: plan
# --------------------------------------------------------------------------- #
TARGET_HINTS = ("strength", "target", "output", "response", "label", "score",
                "quality", "price", "yield", "y")


def detect_columns(header, rows):
    numeric, categorical = [], []
    for col in header:
        vals = [(r.get(col) or "").strip() for r in rows]
        non_empty = [v for v in vals if v]
        if not non_empty:
            categorical.append(col)
            continue
        ok = sum(1 for v in non_empty if parse_float(v) is not None)
        if ok / len(non_empty) >= 0.9:
            numeric.append(col)
        else:
            categorical.append(col)
    return numeric, categorical


def cmd_plan(args):
    header, rows = read_table_render(args.csv)
    load_dictionary(args.dictionary)  # validated now so errors surface early
    numeric, categorical = detect_columns(header, rows)
    class_cols = []
    for col in categorical:
        levels = {(r.get(col) or "").strip() for r in rows}
        levels.discard("")
        if 2 <= len(levels) <= 12:
            class_cols.append(col)
    target = None
    for col in numeric:
        low = col.lower()
        if any(h in low for h in TARGET_HINTS):
            target = col
            break
    if target is None and numeric:
        target = numeric[-1]
    figures = []
    if target:
        figures.append({"id": "fig01", "type": "histogram", "x": target,
                        "title": "%s 分布直方图" % target})
        if class_cols:
            figures.append({"id": "fig02", "type": "box", "y": target,
                            "group": class_cols[0],
                            "title": "%s 按 %s 分组箱线图"
                                     % (target, class_cols[0])})
    if len(numeric) >= 2:
        figures.append({"id": "fig%02d" % (len(figures) + 1),
                        "type": "scatter", "x": numeric[0], "y": numeric[1],
                        "title": "%s 与 %s 散点图" % (numeric[0], numeric[1])})
    task_note = ""
    if args.task:
        if os.path.isfile(args.task):
            task_note = "task file sha256=" + sha256_file(args.task)
        else:
            info("WARNING: task file not found: %s" % args.task)
    plan = {
        "version": 1,
        "draft": True,
        "note": "本计划由 figforge plan 启发式起草，必须由代理人工审阅与修订；"
                "figforge 永不自动改写本文件，render 仅做严格校验。",
        "meta": {"csv": os.path.abspath(args.csv),
                 "csv_sha256": sha256_file(args.csv),
                 "dictionary": os.path.abspath(args.dictionary)
                 if args.dictionary else None,
                 "task": task_note or None,
                 "numeric_columns": numeric,
                 "class_columns": class_cols},
        "figures": figures,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    info("draft plan written: %s (%d figure(s)). Review and edit before "
         "render." % (args.out, len(figures)))


# --------------------------------------------------------------------------- #
# subcommand: render
# --------------------------------------------------------------------------- #
def cmd_render(args):
    header, rows = read_table_render(args.csv)
    dictionary = load_dictionary(args.dictionary)
    plan = load_plan(args.plan)
    csv_sha = sha256_file(args.csv)
    os.makedirs(args.outdir, exist_ok=True)
    formats = []
    for f in (args.formats or "png").split(","):
        f = f.strip().lower()
        if f not in ("png", "svg"):
            die("unsupported format '%s' (allowed: png, svg)" % f)
        if f not in formats:
            formats.append(f)
    mpl, plt = import_matplotlib()
    rendered_with = None
    if mpl is not None:
        set_deterministic_rcparams()
        rendered_with = "matplotlib %s" % mpl.__version__

    entries, anomalies = [], []
    if mpl is None:
        anomalies.append({"code": "matplotlib_missing",
                          "reason": "matplotlib import failed; PNG rendering "
                                    "skipped, data and spec still delivered"})
    for spec in plan["figures"]:
        fid = spec["id"]
        try:
            (data_columns, data_rows, axes, groups, dropped,
             fig_anoms, review) = build_plot_data(spec, header, rows,
                                                  dictionary)
        except ForgeError as exc:
            die(str(exc))
        anomalies.extend(fig_anoms)
        fd_name = "%s.figure_data.csv" % fid
        write_figure_data(os.path.join(args.outdir, fd_name), fid,
                          data_columns, data_rows, dropped, csv_sha)
        files = {}
        status = "rendered"
        if mpl is not None:
            fig = draw_figure(plt, spec, axes, groups, data_columns,
                              data_rows)
            for fmt in formats:
                fname = "%s.%s" % (fid, fmt)
                fig.savefig(os.path.join(args.outdir, fname), format=fmt)
                files[fmt] = fname
            plt.close(fig)
        else:
            status = "figure_not_rendered"
            review.append("figure_not_rendered")
        entry = {
            "id": fid,
            "file": files.get("png") or (files.get("svg")
                                         if files else None),
            "files": files,
            "figure_data": fd_name,
            "type": spec["type"],
            "title": spec.get("title"),
            "status": status,
            "axes": axes,
            "groups": groups,
            "dropped_null_rows": dropped,
            "source_csv_sha256": csv_sha,
            "rendered_with": rendered_with,
            "needs_review": review,
        }
        entries.append(entry)
        info("figure %s: type=%s n=%s dropped=%s status=%s%s"
             % (fid, spec["type"],
                axes["y"]["n_plotted"] if spec["type"] in ("box", "bar")
                else axes["x"]["n_plotted"],
                dropped, status,
                " needs_review=%s" % review if review else ""))
    manifest = {
        "schema_version": 1,
        "tool": TOOL,
        "source_csv": os.path.abspath(args.csv),
        "source_csv_sha256": csv_sha,
        "dictionary": os.path.abspath(args.dictionary)
        if args.dictionary else None,
        "plan": os.path.abspath(args.plan),
        "rendered_with": rendered_with,
        "anomalies": anomalies,
        "figures": entries,
    }
    mpath = os.path.join(args.outdir, "figures_manifest.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    info("manifest written: %s (%d figure(s))" % (mpath, len(entries)))
    if mpl is None:
        sys.exit(3)


# --------------------------------------------------------------------------- #
# subcommand: qc
# --------------------------------------------------------------------------- #
def cmd_qc(args):
    if not os.path.isfile(args.manifest):
        die("manifest not found: %s" % args.manifest)
    with open(args.manifest, "r", encoding="utf-8-sig") as fh:
        manifest = json.load(fh)
    header, rows = read_table_qc(args.csv)
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.manifest))
    failures = [0]

    def check(fid, name, ok, detail=""):
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures[0] += 1
        print("[figforge][qc] %s %s %s%s"
              % (status, fid, name, (" -- " + detail) if detail else ""))

    csv_sha = sha256_file(args.csv)
    check("manifest", "source_csv_sha256",
          manifest.get("source_csv_sha256") == csv_sha,
          "manifest=%s csv=%s" % (manifest.get("source_csv_sha256"), csv_sha))

    for entry in manifest.get("figures", []):
        fid = entry.get("id", "?")
        # 1. PNG existence / size / magic bytes
        png = (entry.get("files") or {}).get("png") or entry.get("file")
        png_path = os.path.join(outdir, png) if png else None
        exists = bool(png_path) and os.path.isfile(png_path)
        check(fid, "png_exists", exists, str(png))
        if exists:
            size = os.path.getsize(png_path)
            check(fid, "png_nonempty", size > 0, "size=%d" % size)
            with open(png_path, "rb") as fh:
                magic = fh.read(8)
            check(fid, "png_magic", magic == PNG_MAGIC, repr(magic))
        # 2. re-derive statistics via the independent QC code path
        ftype = entry.get("type")
        axes = entry.get("axes") or {}
        if ftype == "histogram":
            col = axes["x"]["column"]
            vals = [v for v in (parse_float(x) for x in
                                qc_column_values(header, rows, col))
                    if v is not None]
            n, lo, hi = stats_qc(vals)
            check(fid, "x_n_plotted", n == axes["x"]["n_plotted"],
                  "qc=%d manifest=%s" % (n, axes["x"]["n_plotted"]))
            check(fid, "x_min", lo == axes["x"]["min"],
                  "qc=%r manifest=%r" % (lo, axes["x"]["min"]))
            check(fid, "x_max", hi == axes["x"]["max"],
                  "qc=%r manifest=%r" % (hi, axes["x"]["max"]))
            canonical_n = axes["x"]["n_plotted"]
        elif ftype == "scatter":
            xc, yc = axes["x"]["column"], axes["y"]["column"]
            xs = [parse_float(v) for v in qc_column_values(header, rows, xc)]
            ys = [parse_float(v) for v in qc_column_values(header, rows, yc)]
            pairs = [(a, b) for a, b in zip(xs, ys)
                     if a is not None and b is not None]
            for axis, vals in (("x", [p[0] for p in pairs]),
                               ("y", [p[1] for p in pairs])):
                n, lo, hi = stats_qc(vals)
                check(fid, "%s_n_plotted" % axis,
                      n == axes[axis]["n_plotted"],
                      "qc=%d manifest=%s" % (n, axes[axis]["n_plotted"]))
                check(fid, "%s_min" % axis, lo == axes[axis]["min"],
                      "qc=%r manifest=%r" % (lo, axes[axis]["min"]))
                check(fid, "%s_max" % axis, hi == axes[axis]["max"],
                      "qc=%r manifest=%r" % (hi, axes[axis]["max"]))
            canonical_n = axes["x"]["n_plotted"]
        elif ftype in ("box", "bar"):
            groups = entry.get("groups") or {}
            gc = groups.get("column")
            yc = axes["y"]["column"]
            gs = qc_column_values(header, rows, gc)
            ys = [parse_float(v) for v in qc_column_values(header, rows, yc)]
            counts, vals = {}, []
            for g, v in zip(gs, ys):
                g = (g or "").strip()
                if not g or v is None:
                    continue
                counts[g] = counts.get(g, 0) + 1
                vals.append(v)
            n, lo, hi = stats_qc(vals)
            check(fid, "y_n_plotted", n == axes["y"]["n_plotted"],
                  "qc=%d manifest=%s" % (n, axes["y"]["n_plotted"]))
            check(fid, "y_min", lo == axes["y"]["min"],
                  "qc=%r manifest=%r" % (lo, axes["y"]["min"]))
            check(fid, "y_max", hi == axes["y"]["max"],
                  "qc=%r manifest=%r" % (hi, axes["y"]["max"]))
            check(fid, "group_levels",
                  sorted(counts) == (groups.get("levels") or []),
                  "qc=%s manifest=%s" % (sorted(counts),
                                         groups.get("levels")))
            check(fid, "group_counts", counts == (groups.get("counts") or {}),
                  "qc=%s manifest=%s" % (counts, groups.get("counts")))
            canonical_n = axes["y"]["n_plotted"]
        else:
            check(fid, "known_type", False, "type=%r" % ftype)
            canonical_n = None
        # 3. axis label contains the dictionary unit string when defined
        for axis in ("x", "y"):
            ax = axes.get(axis) or {}
            unit = ax.get("unit")
            if unit:
                check(fid, "%s_label_has_unit" % axis,
                      unit in (ax.get("axis_text") or ""),
                      "unit=%r label=%r" % (unit, ax.get("axis_text")))
        # 4. figure_data CSV row count == n_plotted
        fd = entry.get("figure_data")
        fd_path = os.path.join(outdir, fd) if fd else None
        fd_ok = bool(fd_path) and os.path.isfile(fd_path)
        check(fid, "figure_data_exists", fd_ok, str(fd))
        if fd_ok and canonical_n is not None:
            n_rows = count_figure_data_rows(fd_path)
            check(fid, "figure_data_rows", n_rows == canonical_n,
                  "qc=%d manifest=%s" % (n_rows, canonical_n))
    total = failures[0]
    print("[figforge][qc] %s: %d failed check(s)"
          % ("FAIL" if total else "PASS", total))
    sys.exit(1 if total else 0)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(
        prog=TOOL,
        description="Deterministic, data-dictionary-bound figure renderer "
                    "with QC. All errors are prefixed with [figforge].")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp, dictionary=True):
        sp.add_argument("--csv", required=True, help="input CSV snapshot")
        if dictionary:
            sp.add_argument("--dictionary", default=None,
                            help="data dictionary (JSON {columns:{...}} or "
                                 "CSV name,label,unit)")

    sp = sub.add_parser("plan", help="draft a figure plan from CSV columns "
                                     "and the data dictionary")
    add_common(sp)
    sp.add_argument("--task", default=None, help="task.md (recorded in meta)")
    sp.add_argument("--out", required=True, help="output plan JSON path")
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("render", help="validate plan and render figures "
                                       "deterministically")
    add_common(sp)
    sp.add_argument("--plan", required=True, help="figure plan JSON")
    sp.add_argument("--outdir", required=True, help="output directory")
    sp.add_argument("--formats", default="png",
                    help="comma-separated output formats: png,svg "
                         "(default png)")
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("qc", help="re-derive every manifest claim from the "
                                   "CSV and verify artifacts")
    sp.add_argument("--manifest", required=True, help="figures_manifest.json")
    sp.add_argument("--csv", required=True, help="original CSV snapshot")
    sp.add_argument("--outdir", default=None,
                    help="directory holding PNG/figure_data files "
                         "(default: manifest directory)")
    sp.set_defaults(func=cmd_qc)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except ForgeError as exc:
        die(str(exc))
    except BrokenPipeError:
        sys.exit(0)


if __name__ == "__main__":
    main()
