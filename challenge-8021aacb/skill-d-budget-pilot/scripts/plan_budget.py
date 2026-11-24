#!/usr/bin/env python3
"""plan_budget.py -- 盘点输入并生成预算编排计划。

平台预算硬约束: 64 次模型请求 / 900 秒 / 每响应 16384 tokens。
本脚本按输入材料规模给出六阶段的请求/秒数分配与检查点时刻表,
让 Agent 在任何时刻知道「该做到哪一步、还剩多少余量」。

用法:
    python3 plan_budget.py INPUT_DIR PLAN_JSON [--requests 64] [--seconds 900]
"""
import argparse
import json
import os

# 阶段: (名称, 请求占比, 秒占比, 该阶段结束时的检查点动作)
PHASES = [
    ('contract_and_inventory', 0.05, 0.05, 'partial result.json 已写, 契约字段抄录完毕'),
    ('extraction',             0.10, 0.20, '稿件文本与锚点/块库就位, 抽取异常已记 uncertainty'),
    ('diagnosis_core',         0.45, 0.40, '六维诊断初稿完成, high 子类优先'),
    ('verification',           0.15, 0.15, '引文/字段机器校验通过, 误报已排除'),
    ('deliverables',           0.20, 0.15, '编辑计划/决策表等产物生成并目检'),
    ('finalize',               0.05, 0.05, 'result.json 收尾, 状态诚实, 自查清单过'),
]


def plan(input_dir, plan_path, requests, seconds):
    inventory = []
    total_bytes = 0
    for name in sorted(os.listdir(input_dir)):
        p = os.path.join(input_dir, name)
        if os.path.isfile(p):
            sz = os.path.getsize(p)
            total_bytes += sz
            inventory.append({'file': name, 'bytes': sz})

    # 材料越大, diagnosis_core 占比上调, 从 deliverables 借
    big = total_bytes > 200_000
    phases = []
    used_r = used_s = 0
    for i, (name, fr, fs, gate) in enumerate(PHASES):
        r = fr + (0.10 if big and name == 'diagnosis_core' else 0)
        s = fs + (0.05 if big and name == 'extraction' else 0)
        if big and name == 'deliverables':
            r -= 0.10
            s -= 0.05
        used_r += r
        used_s += s
        phases.append({'phase': name,
                       'request_budget': max(1, round(requests * r)),
                       'second_budget': round(seconds * s),
                       'exit_gate': gate})
    scale_r = requests / sum(p['request_budget'] for p in phases)
    for p in phases:
        p['request_budget'] = max(1, round(p['request_budget'] * scale_r))
    phases[-1]['request_budget'] += requests - sum(p['request_budget'] for p in phases)

    doc = {'budget': {'requests': requests, 'seconds': seconds,
                      'tokens_per_response': 16384},
           'input_inventory': inventory, 'input_bytes': total_bytes,
           'large_input': big, 'phases': phases,
           'rules': [
               '每阶段出口必须满足 exit_gate 才进入下一阶段',
               '任一时刻 /app/output/result.json 都是有效 JSON',
               '实际请求数超过该阶段预算 150% 时触发 degradation_ladder.md',
           ]}
    with open(plan_path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(json.dumps({'files': len(inventory), 'bytes': total_bytes,
                      'phases': len(phases)}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input_dir')
    ap.add_argument('plan')
    ap.add_argument('--requests', type=int, default=64)
    ap.add_argument('--seconds', type=int, default=900)
    a = ap.parse_args()
    plan(a.input_dir, a.plan, a.requests, a.seconds)


if __name__ == '__main__':
    main()
