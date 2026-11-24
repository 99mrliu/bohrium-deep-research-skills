#!/usr/bin/env python3
"""normalize_units.py — 单位归一化（bundle C 签名脚本 2）。

读 work/quant_candidates.jsonl，按 vocab/units.json 为每个候选增加：
  value_canonical / unit_canonical / dimension / norm_status（及 ci/sd 的 canonical）。
规则：
  - 有单位且单位在词表：value_canonical = value * factor。
  - 无单位但指标在 metric_terms.json 的 dimension_defaults：按默认量纲归一（factor=1）。
  - sample_size → dimension=count；pvalue → dimension=pvalue。
  - 其余（未知单位、无单位且无默认量纲）：norm_status=unnormalized，禁止跨文献比较。
产物：work/quant_normalized.jsonl。仅用标准库。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def run(work):
    units_vocab = load_json(os.path.join(HERE, "..", "vocab", "units.json"))
    units = units_vocab["units"]
    dim_unit = units_vocab["dimension_canonical_unit"]
    metric_vocab = load_json(os.path.join(HERE, "..", "vocab", "metric_terms.json"))
    dim_defaults = metric_vocab.get("dimension_defaults", {})

    rows = load_jsonl(os.path.join(work, "quant_candidates.jsonl"))
    for r in rows:
        r.update(value_canonical=None, unit_canonical=None, dimension=None,
                 ci_low_canonical=None, ci_high_canonical=None, sd_canonical=None,
                 norm_status="unnormalized", norm_note=None)
        factor, dim = None, None
        if r["kind"] == "sample_size":
            factor, dim, r["unit_canonical"] = 1.0, "count", "count"
        elif r["kind"] == "pvalue":
            factor, dim, r["unit_canonical"] = 1.0, "pvalue", "pvalue"
        elif r.get("unit"):
            u = r["unit"].lower()
            if u in units:
                factor = units[u]["factor"]
                dim = units[u]["dimension"]
                r["unit_canonical"] = units[u]["canonical"]
            else:
                r["norm_note"] = f"unknown_unit:{r['unit']}"
        else:
            dim = dim_defaults.get(r.get("metric"))
            if dim:
                factor = 1.0
                r["unit_canonical"] = dim_unit.get(dim, dim)
                r["norm_note"] = "implicit_dimension_default"
            else:
                r["norm_note"] = "no_unit_no_default_dimension"
        if factor is not None:
            r["value_canonical"] = r["value"] * factor
            r["dimension"] = dim
            r["norm_status"] = "ok"
            if r.get("ci_low") is not None:
                r["ci_low_canonical"] = r["ci_low"] * factor
                r["ci_high_canonical"] = r["ci_high"] * factor
            if r.get("sd") is not None:
                r["sd_canonical"] = r["sd"] * factor

    out_path = os.path.join(work, "quant_normalized.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    rows = run(args.work)
    by_dim, unnorm = {}, 0
    for r in rows:
        if r["norm_status"] == "ok":
            by_dim[r["dimension"]] = by_dim.get(r["dimension"], 0) + 1
        else:
            unnorm += 1
    print(json.dumps({"normalized": len(rows) - unnorm, "unnormalized": unnorm,
                      "by_dimension": by_dim}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
