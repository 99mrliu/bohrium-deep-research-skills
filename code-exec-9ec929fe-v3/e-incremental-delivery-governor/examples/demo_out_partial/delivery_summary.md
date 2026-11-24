# 交付摘要（delivery summary）

- case_id: SYNTH-GOV-001
- 状态: **partial**
- finalize 时间(UTC): 2026-11-24T15:51:15+00:00
- 输入 case.json sha256: `95497db94c08df8890b6814d2d923cf96b7d2059037f2009b52415741b0c49af`
- 工具: stagegate 1.0.0；Python 3.12.14；平台 darwin

## 字段明细

| 字段 | 状态 | 证据 | 缺失原因 |
| --- | --- | --- | --- |
| case_id | 已填充 | （无） | — |
| cleaned_table | 已填充 | cleaned.csv | — |
| statistics | 已填充 | stats.json | — |
| figures | 缺失 | — | 绘图后端不可用且预算不足以修复；保持 null 并在此给出理由，绝不静默缺省 |
| status | 治理器维护 | — | — |
| anomalies | 治理器维护 | — | — |
| provenance | 治理器维护 | — | — |
| notes | 已填充 | （无） | — |

## 异常（anomalies，2 条）

- [2026-11-24T15:51:12+00:00] stage_command_failed：/Users/liuhengshen/.bohrium/python/shims/5dc017c31b86/python3 -c 'import sys; print("boom: plotting backend unavailable", file=sys.stderr); sys.exit(3)' exited 3
- [2026-11-24T15:51:13+00:00] figure_backend_missing：合成演示：绘图后端不可用，figures 字段在本轮预算内无法产出

## 命令日志摘要（journal digest）

- 命令总数: 2；失败: 1；总耗时: 0.627 秒

| # | exit | duration_s | cmd |
| --- | --- | --- | --- |
| 1 | 0 | 0.311 | `/Users/liuhengshen/.bohrium/python/shims/5dc017c31b86/python3 /Users/liuhengshen/Desktop/bhr_product/3rd/4/submit/skills-9ec929fe-v3/e-incremental-delivery-governor/examples/toy_analysis.py --csv /Users/liuhengshen/Desktop/bhr_product/3rd/4/submit/skills-9ec929fe-v3/e-incremental-delivery-governor/examples/synthetic_case/measurements_syn.csv --out /Users/liuhengshen/Desktop/bhr_product/3rd/4/submit/skills-9ec929fe-v3/e-incremental-delivery-governor/examples/demo_out_partial` |
| 2 | 3 | 0.316 | `/Users/liuhengshen/.bohrium/python/shims/5dc017c31b86/python3 -c 'import sys; print("boom: plotting backend unavailable", file=sys.stderr); sys.exit(3)'` |

## 本次 partial 的边界

- `figures`：绘图后端不可用且预算不足以修复；保持 null 并在此给出理由，绝不静默缺省
