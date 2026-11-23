#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成示例（synthetic），非正式案例结果：模拟“能正常产出指标”的候选数值方法。
仅打印写死的演示指标并退出 0，不代表任何真实论文的数值复现。"""
import json

metrics = {
    "candidate": "method_ok",
    "synthetic": True,
    "metrics": {"accuracy": 0.901, "rmse": 0.124, "runtime_seconds": 0.01},
}
print(json.dumps(metrics, ensure_ascii=False, indent=2))
print("method_ok: synthetic demo finished successfully.")
raise SystemExit(0)
