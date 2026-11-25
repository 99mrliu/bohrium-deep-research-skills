# 合成示例逐步演练（SYNTHETIC, not real papers, 非正式案例结果）

> 本示例全部文献为虚构，DOI 使用 `10.0000/synth.*` 保留段。`examples/run_out/` 下的
> 产物是本示例的**真实脚本运行结果**（作者在 macOS + Python 3 标准库、全程离线下执行），
> 仅用于演示流程，不冒充正式案例结果。

以下命令均假设 cwd 为 bundle 根目录（脚本位置无关，也可用绝对路径调用）。

## 1. 正常全流程

```bash
python3 scripts/warden.py --case examples/case.json --roots examples/corpus \
    --out examples/run_out/output --workdir examples/run_out/work --max-depth 2
```

实际输出（退出码 0）：

```
warden done: status=ok candidates=6 edges=14 stubs=1
```

产物核对要点：

- `run_out/output/result.json`：`status=ok`；候选 6 条——种子 synth.001（hop 0）、
  一层后向出处 synth.002 / synth.004（via reference 边）、一层前向后续 synth.003
  （via 反向索引恢复的 citation 边，`direction_restored: true`）、二层平行工作
  synth.005、以及 stub synth.404（故意不可解析，仅保留原始指针与 locator）；
- 跨库去重：synth.002 同时出现在 `crossref_batch.json` 与 `openalex_nodes.jsonl`，
  按 DOI 规范化键合并为单条记录；
- `contract` 覆盖 output_contract 全部 9 个字段，`review_notes` 按契约置空并记入
  uncertainty；
- `run_out/work/checkpoints/stage{0,1,2,3}.json` 各含阶段号、完成时间与产物 sha1；
- 时间戳只出现在 `run_out/work/run_log.json` 与 checkpoint 中，result.json 内没有。

## 2. 模拟中断后 `--resume` 续跑

```bash
# 模拟 stage3 完成前中断：删除 stage3 checkpoint 与最终产物
rm examples/run_out/work/checkpoints/stage3.json examples/run_out/output/result.json

# 断点续跑：stage0–2 从 checkpoint 载荷重建，仅补跑 stage3
python3 scripts/warden.py --case examples/case.json --roots examples/corpus \
    --out examples/run_out/output --workdir examples/run_out/work --max-depth 2 --resume
```

实际验证：续跑前后 result.json 的 sha1 均为
`4cd04abafca2a6a10590a031038a5efa21f48e9a` —— 续跑产物与一气呵成**逐字节一致**
（该哈希对应 QC 追加 uncertainty 之前的 warden 原始产物）。

## 3. QC 质量回路

```bash
python3 scripts/qc_loop.py --case examples/case.json \
    --out examples/run_out/output --workdir examples/run_out/work
```

首次实际输出（退出码 0）：`ok=true (auto_fixed=1 critical_open=0 major_open=0)`。
Q1–Q7 全部通过；Q3b 发现契约字段 `review_notes` 为 null（管线本无此产物，属契约
允许的空值），按策略写入一条 uncertainty 提示人工确认。再次运行幂等：
`ok=true (auto_fixed=0 ...)`，不重复追加。报告见 `run_out/work/qc_report.json`
与人读版 `qc_report.md`（run_out 中保留的是 QC 之后的最终状态）。

## 4. 双跑一致性校验

```bash
python3 scripts/reproduce.py --case examples/case.json --roots examples/corpus \
    --max-depth 2 --workdir examples/run_out/work
```

实际输出（退出码 0）：`identical=true runs=2 diffs=0`。两次隔离运行的 result.json
均为 26482 字节且逐字节一致；报告见 `run_out/work/reproduce_report.json`。

## 5. 预算降级演示（可选）

```bash
python3 scripts/warden.py --case examples/case.json --roots examples/corpus \
    --out /tmp/wq/out --workdir /tmp/wq/work --time-budget 1
```

实际行为：stage0 的 honest partial 照常落盘，stage1 因剩余预算不足 margin 被跳过，
结果为 `status=partial`、`completed_stage=0`、`budget_limited=true`，只有 stage0
checkpoint；之后去掉 `--time-budget 1` 加 `--resume` 即可补齐后续阶段——降级跳过的
阶段不写 checkpoint，续跑时会重新尝试，不会造成永久缺失。
