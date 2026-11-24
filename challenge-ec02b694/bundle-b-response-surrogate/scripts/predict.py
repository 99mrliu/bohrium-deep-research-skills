#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""predict.py -- 用 surrogate.json 对候选点做预测，强制披露不确定度与外推风险。

行为：
  - rsm 模式：编码候选点 -> 特征向量 -> 预测值 + 95% 预测区间；
  - 候选点越出训练有效域盒 -> extrapolation=true，区间按 (1 + 3*相对越界距离) 放大，
    并附警告 "该预测为待确认假设，不得作为可执行事实"；
  - fallback 模式（样本不足/奇异降级）-> 强制 extrapolation 级警告，
    预测 = 最近邻（平局取均值，无近邻用总均值），区间 = max(3*std, 0.5*range)；
  - 任何异常输入都输出带 warning 的 prediction.json，绝不 traceback。

用法：
  python3 predict.py --surrogate surrogate.json --point '{"temp_C": 70, "time_h": 8}' \
      --out prediction.json
  python3 predict.py --surrogate surrogate.json --points candidates.json --out prediction.json
"""
import argparse
import json
import math
import os
import sys

EXTRAPOLATION_NOTICE = ("该预测为待确认假设，不得作为可执行事实；"
                        "候选点位于代理模型有效域之外（或模型处于降级模式），"
                        "必须安排实测确认后方可用于决策。")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def t_crit(df):
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
             13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
             19: 2.093, 20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000,
             120: 1.980}
    if df is None or df < 1:
        return None
    for k in sorted(table):
        if df <= k:
            return table[k]
    return 1.96


def encode_point(point, coding, factors):
    """按 surrogate 中的编码规则把原始点编码到 [-1,1] 尺度。"""
    x = []
    missing = []
    for f in factors:
        v = point.get(f)
        if v is None:
            missing.append(f)
            x.append(0.0)
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            missing.append("%s(非数值:%r)" % (f, v))
            x.append(0.0)
            continue
        c = coding.get(f, {})
        lo, hi = c.get("min"), c.get("max")
        if lo is None or hi is None or hi - lo < 1e-15:
            x.append(0.0)
        else:
            x.append(2.0 * (v - 0.5 * (lo + hi)) / (hi - lo))
    return x, missing


def term_value(powers, x):
    v = 1.0
    for pw, xi in zip(powers, x):
        v *= xi ** pw
    return v


def domain_check(point, domain, factors):
    """返回 (outside: bool, rel_excess: float, detail: list)。"""
    box = (domain or {}).get("box") or {}
    outside = False
    rel_excess = 0.0
    detail = []
    for f in factors:
        if f not in box:
            continue
        lo, hi = box[f]
        v = point.get(f)
        try:
            v = float(v)
        except (TypeError, ValueError):
            detail.append("%s 缺值/非数值，无法判定域" % f)
            outside = True
            rel_excess = max(rel_excess, 1.0)
            continue
        span = hi - lo if hi - lo > 1e-15 else 1.0
        if v < lo:
            outside = True
            rel_excess = max(rel_excess, (lo - v) / span)
            detail.append("%s=%g 低于训练下限 %g" % (f, v, lo))
        elif v > hi:
            outside = True
            rel_excess = max(rel_excess, (v - hi) / span)
            detail.append("%s=%g 高于训练上限 %g" % (f, v, hi))
        else:
            detail.append("%s=%g 在 [%g, %g] 内" % (f, v, lo, hi))
    return outside, rel_excess, detail


def predict_rsm(surr, point):
    factors = surr["factors"]
    x, missing = encode_point(point, surr.get("coding", {}), factors)
    powers = surr["term_powers"]
    beta = [surr["coefficients"][t] for t in surr["terms"]]
    feats = [term_value(p, x) for p in powers]
    yhat = sum(b * f for b, f in zip(beta, feats))

    warnings_ = []
    if missing:
        warnings_.append("候选点缺少因子 %s，已按域中心处理；预测不可信" % ", ".join(missing))

    sigma2 = surr.get("sigma2")
    df = surr.get("df_error")
    tc = t_crit(df)
    lev = None
    inv = surr.get("inv_xtx")
    if inv is not None:
        lev = 0.0
        for i in range(len(feats)):
            for j in range(len(feats)):
                lev += feats[i] * inv[i][j] * feats[j]
        lev = max(0.0, lev)
    if sigma2 is None or tc is None:
        half = None
        warnings_.append("sigma2 或自由度不可用，无法构造数值预测区间")
    else:
        var_pred = sigma2 * (1.0 + (lev if lev is not None else 1.0 / max(1, surr.get("n_used", 1))))
        if lev is None:
            warnings_.append("(X'X)^-1 不可用，杠杆值按 1/n 近似，区间偏窄，谨慎使用")
        half = tc * math.sqrt(max(var_pred, 0.0))

    outside, rel_excess, detail = domain_check(point, surr.get("valid_domain"), factors)
    extrapolation = outside
    if outside and half is not None:
        half = half * (1.0 + 3.0 * rel_excess)
        warnings_.append(EXTRAPOLATION_NOTICE)
        warnings_.append("区间已按 (1 + 3*%.3f) 放大" % rel_excess)
    return {
        "mode": "rsm",
        "point": point,
        "coded_point": x,
        "prediction": yhat,
        "interval_95": ([yhat - half, yhat + half] if half is not None else None),
        "extrapolation": extrapolation,
        "domain_check": detail,
        "leverage": lev,
        "warnings": warnings_,
    }


def predict_fallback(surr, point):
    factors = surr.get("factors", [])
    pts = surr.get("training_points", [])
    warnings_ = [
        "代理模型处于降级模式（%s）" % surr.get("fallback_reason", "原因未记录"),
        EXTRAPOLATION_NOTICE,
        "样本不足，预测仅供假设；输出强制使用 extrapolation 级警告",
    ]
    estimate = surr.get("mean_response")
    method = "global-mean"
    if pts:
        best_d, best_ys = None, []
        box = (surr.get("valid_domain") or {}).get("box") or {}
        for rec in pts:
            d2 = 0.0
            ok = True
            for f, xv in zip(factors, rec.get("x", [])):
                pv = point.get(f)
                try:
                    pv = float(pv)
                except (TypeError, ValueError):
                    ok = False
                    break
                lo, hi = (box.get(f) or [0.0, 1.0])
                span = hi - lo if hi - lo > 1e-15 else 1.0
                d2 += ((pv - xv) / span) ** 2
            if not ok:
                continue
            if best_d is None or d2 < best_d - 1e-15:
                best_d, best_ys = d2, [rec.get("y")]
            elif abs(d2 - best_d) <= 1e-15:
                best_ys.append(rec.get("y"))
        if best_ys:
            estimate = sum(best_ys) / len(best_ys)
            method = "nearest-neighbor(k=%d, normalized distance=%.4g)" % (len(best_ys),
                                                                           math.sqrt(best_d or 0.0))
    std = surr.get("std_response")
    rng = surr.get("data_range")
    spread = None
    if std is not None and rng is not None:
        spread = max(3.0 * std, 0.5 * (rng[1] - rng[0]))
    elif rng is not None:
        spread = 0.5 * (rng[1] - rng[0])
    interval = ([estimate - spread, estimate + spread]
                if (estimate is not None and spread is not None) else None)
    if interval is None:
        warnings_.append("无可估的散布尺度，无法给出数值区间")
    return {
        "mode": "fallback",
        "estimator": method,
        "point": point,
        "prediction": estimate,
        "interval_95_nominal": interval,
        "interval_notice": "降级模式区间为探索性尺度（max(3*std, 0.5*range)），不是统计意义的 95% 区间",
        "extrapolation": True,
        "forced_extrapolation_level_warning": True,
        "warnings": warnings_,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="代理模型预测（强制不确定度与外推披露）")
    parser.add_argument("--surrogate", required=True, help="surrogate.json 路径")
    parser.add_argument("--point", help="单个候选点 JSON，如 '{\"temp_C\":70}'")
    parser.add_argument("--points", help="候选点 JSON 文件（list 或 {\"points\":[...]}）")
    parser.add_argument("--out", default="prediction.json", help="输出路径")
    args = parser.parse_args(argv)

    exit_code = 0
    try:
        surr = load_json(args.surrogate)
    except Exception as exc:  # noqa: BLE001
        surr = None
        surr_err = "surrogate.json 读取失败: %s: %s" % (args.surrogate, exc)
    else:
        surr_err = None

    points = []
    load_errors = []
    if args.point:
        try:
            points.append(json.loads(args.point))
        except Exception as exc:  # noqa: BLE001
            load_errors.append("--point JSON 解析失败: %s" % exc)
    if args.points:
        try:
            raw = load_json(args.points)
            if isinstance(raw, dict):
                raw = raw.get("points", [])
            if isinstance(raw, list):
                points.extend(raw)
            else:
                load_errors.append("--points 文件不是列表")
        except Exception as exc:  # noqa: BLE001
            load_errors.append("--points 读取失败: %s" % exc)
    if not points and not load_errors:
        load_errors.append("未提供任何候选点（--point 或 --points）")

    predictions = []
    if surr is None:
        exit_code = 2
        for pt in points or [{}]:
            predictions.append({
                "mode": "error", "point": pt, "prediction": None, "interval_95": None,
                "extrapolation": True,
                "warnings": [surr_err, EXTRAPOLATION_NOTICE,
                             "无模型可用，任何数值都不得引用"],
            })
    else:
        mode = surr.get("mode")
        for pt in points:
            try:
                if not isinstance(pt, dict):
                    raise ValueError("候选点必须是对象: %r" % (pt,))
                if mode == "rsm":
                    predictions.append(predict_rsm(surr, pt))
                else:
                    predictions.append(predict_fallback(surr, pt))
                    exit_code = max(exit_code, 1)
            except Exception as exc:  # noqa: BLE001
                predictions.append({
                    "mode": "error", "point": pt, "prediction": None, "interval_95": None,
                    "extrapolation": True,
                    "warnings": ["该候选点预测失败: %r" % (exc,), EXTRAPOLATION_NOTICE],
                })
                exit_code = max(exit_code, 1)

    any_extrap = any(p.get("extrapolation") for p in predictions)
    output = {
        "schema_version": "1.0",
        "generated_by": "predict.py",
        "surrogate_mode": (surr or {}).get("mode"),
        "n_points": len(predictions),
        "any_extrapolation": any_extrap,
        "global_notice": ("模型预测不是实测值；任何用于实验计划的数值都必须"
                          "标注 [模型预测] 并携带不确定区间。"),
        "load_errors": load_errors,
        "predictions": predictions,
    }
    if any_extrap:
        output["extrapolation_notice"] = EXTRAPOLATION_NOTICE
        exit_code = max(exit_code, 1)

    try:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(output, fh, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("写出 %s 失败: %s\n" % (args.out, exc))
        print(json.dumps(output, ensure_ascii=False))
        return 2

    for p in predictions:
        sys.stderr.write("predict: point=%s -> %s (mode=%s, extrapolation=%s)\n"
                         % (p.get("point"), p.get("prediction"), p.get("mode"),
                            p.get("extrapolation")))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
