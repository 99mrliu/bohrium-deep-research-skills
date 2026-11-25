---
name: budget-run-governor
description: 预算感知运行调度器。当需要在硬预算（64 次模型请求 / 900 秒墙钟 / 单次响应 16384 tokens）内跑完一次全量题录筛选、且任何时刻都必须有诚实可交付物时使用。方法链：plan_run 生成阶段 DAG 与请求/墙钟估算并预选降级档位 → budget_ledger 逐次记账、预留 reserve、发出 ok/warn/critical 降级信号 → checkpoint 按 sha256 校验产物、支持断点续跑 → flush_partial 每阶段增量落盘 result.json（in_progress→completed/partial）→ L0–L3 降级阶梯按写死规则缩减范围并如实表述。边界：只调度执行过程与预算，不做判定内容、不做诊断分析、不做渲染，绝不伪造"已完成"。
---

# budget-run-governor：预算感知运行调度器

## 1. 适用场景与边界（红线）

**适用**：评测/生产环境中一次有硬预算的系统性文献筛选运行——固定研究问题、
全量题录筛选、可能含组织方标注的合成重复导出与冲突双人意见夹具。
平台要求"尽早保存诚实 partial 并增量改进"，本技能把该要求做成可执行机制。

**边界（红线）**：
- 本技能**只调度执行过程与预算**：不做判定内容本身、不做诊断分析、不做渲染；
- **绝不伪造"已完成"**：降级、中断、字段缺失必须如实写进 status 与 uncertainty
  （模板见 `references/degradation_ladder.md` §3）；
- 不得挪用 reserve（fill 1 次 + final_check 1 次请求）；不得删除 output_contract
  要求的任何字段，填不了填 `null` 并说明；不得伪造人工复核结论。

## 2. 运行环境

- Python 3 标准库，无第三方依赖；全部脚本 UTF-8、无符号链接、无二进制；
- 退出码统一：`0` 成功；`2` 用法/输入错误（含台账未初始化、重复 init）；
  `3` 运行时失败（含模拟崩溃、产物校验不通过）；
- 路径默认值可被参数或环境变量覆盖：`--case`（BRG_CASE，默认 `/input/case.json`）、
  `--work`（BRG_WORK，默认 `/app/work`）、`--output`（BRG_OUTPUT，默认 `/app/output`）；
- 幂等：plan/flush/selfcheck 由当前产物决定、重复执行同结果；checkpoint record
  覆盖同名阶段；ledger init 需 `--force` 才重置（**续跑时禁止重置台账**）；
- 所有脚本顶层 try/except 兜底：意外一律 exit 3，不留半写文件（写盘均先 tmp 后 replace）。

## 3. 工作流程

调度器**包裹**案例实质工作：实质阶段（判定/诊断等 [模型] 工作）由其他技能完成，
本调度器在每一阶段前后执行记账、落盘与检查点。

1. **[脚本] plan**：`plan_run.py` 读 case.json，分解阶段 DAG
   （inventory→scaffold→normalize→dedupe→decide→diagnose→fill→final_check），
   按 N 估算请求数（decide = ceil(N/batch)）与墙钟，生成 `run_plan.json`，
   超预算风险时预选 L1/L2/L3（估算公式见 `references/budget_model.md`）。
2. **[脚本] 台账初始化**：`budget_ledger.py init --reserve 2`，写入预算与预留。
3. **[脚本] 骨架落盘**：`flush_partial.py` 先把 status=in_progress 的合法骨架
   result.json 落进 /app/output——**从这一刻起任何中断都有合法交付**。
4. **循环 [执行阶段 → ledger → checkpoint → flush]**（按计划拓扑序）：
   - [模型]/[脚本] 执行阶段实质工作（产出 work/<stage>.json）；
   - [脚本] `budget_ledger.py charge` 记账；若返回 warn/critical 信号，
     按降级阶梯降档（跳过低优先级阶段，critical 直接转 L3 收尾）；
   - [脚本] `checkpoint.py record` 记录阶段产物 sha256（先固化检查点，
     保证落盘的 result.json 与崩溃安全状态一致）；
   - [脚本] `flush_partial.py` 增量落盘当前最好结果。
5. **[脚本] 终检与最终落盘**：final_check 核对合同字段在位性；`flush_partial.py`
   落最终 status（completed；L3 或未满完成条件而终止则 partial）。
6. **[脚本] 收尾**：`budget_ledger.py status` 输出台账汇总，随 result.json
   的 `scheduler` 块一并交付。

## 4. 输出合同映射

result.json 由 `flush_partial.py` 组装：output_contract 要求的字段一个不少。

| 合同字段 | 来源产物 | 缺失时的诚实处理 |
|---|---|---|
| case_id | case.json | —（必有） |
| status | 检查点+档位推导 | in_progress / completed / partial，见 §3.5 |
| decisions | work/decisions.json | null + uncertainty 说明（未执行或档位未启用） |
| screening_summary | inventory.json + decisions.json 计数 | null + 说明 |
| dedup_report | work/dedup_report.json | null + 说明 |
| sources | work/inventory.json | null + 说明 |
| uncertainty | 缺失标注 + 降级声明 + uncertain 记录 | 空数组（无问题） |
| change_records | work/change_records.jsonl | 空数组 |
| notes | 调度器边界声明 | — |

附加 `scheduler` 块（合同外元信息，不删合同字段）：档位、批量、已完成/待办阶段、
台账摘要（spent/remaining/reserve/elapsed）。

## 5. 异常处理表

| 异常 | 检测点 | 处置 |
|---|---|---|
| 墙钟将超时 | ledger status：elapsed ≥ 75%/90% → warn/critical | warn 降一级；critical 转 L3，仅 fill+final_check 收尾落盘 |
| 模型请求将超预算 | ledger status：remaining < reserve+未完成最小请求 → warn；remaining ≤ reserve → critical | 同上；reserve 永不被挪用 |
| 崩溃/中断续跑 | checkpoint verify / resume-point：产物缺失或 sha256 不一致 | 从最早问题阶段重跑，其后阶段一并重跑；完好阶段不重来；台账不重置 |
| 阶段失败（exit≠0） | 驱动循环捕获非零退出 | 立即 `flush_partial.py --final` 落 partial（status=partial + 原因），exit 3 |
| 输入非法 | plan_run / flush 解析 case.json 失败 | exit 2，不写任何产物 |
| 台账误重置 | ledger init 检测到已有台账且无 --force | 拒绝并提示，exit 2 |

## 6. 最小调用示例

```bash
# 端到端（以合成示例为例；真实运行时 case 在 /input/case.json）
python3 scripts/simulate_stages.py \
  --case examples/case.json --root examples/run_full \
  --budget-requests 64 --budget-seconds 900        # → exit 0

# 单脚本手动链（等价内核）
python3 scripts/plan_run.py --case /input/case.json --work /app/work
python3 scripts/budget_ledger.py --work /app/work init --reserve 2
python3 scripts/flush_partial.py --case /input/case.json --work /app/work --output /app/output
python3 scripts/budget_ledger.py --work /app/work charge --stage decide --requests 3 --seconds 41
python3 scripts/checkpoint.py --work /app/work record --stage decide --outputs /app/work/decisions.json
python3 scripts/checkpoint.py --work /app/work resume-point   # 中断后定位续跑起点
python3 scripts/selfcheck.py                                   # 平台约束自查
```

## 7. 维护信息

- 版本：v1.0.0（2026-11-25）
- 维护者：bohrium-deep-research-skills 项目组
- 参考：`references/budget_model.md`（预算模型）、
  `references/degradation_ladder.md`（降级阶梯与诚实表述模板）、
  `examples/example_walkthrough.md`（合成示例全程演示，含中断续跑）。
