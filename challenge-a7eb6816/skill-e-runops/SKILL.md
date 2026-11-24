---
name: runops-honest-degradation
description: >-
  科研成果转化写作任务在受限预算（模型请求数 / 墙钟时间 / 响应长度）下运行，
  需要输入异常识别（材料缺失 / 跨文件数值冲突 / 涉密未发表 / 篇幅约束冲突）、
  分阶段管线断点续跑、以及在任何时刻都能交付诚实 partial 的 result.json 时
  使用本 Skill。适用于评测机只读输入、标准库-only、无第三方包的受限环境。
---

# RunOps：运行可靠性与诚实降级

## 重心与边界

**重心**：让科研成果转化写作管线在受限预算下"跑得完、断得明、说得实"。

- 输入异常先分流，再动笔：缺材料、数值打架、涉密标记、字数装不下，各有固定处置。
- 分阶段执行 + 每阶段检查点：崩溃后 `--resume` 只重跑受影响阶段，不浪费预算。
- **任何时刻** `/app/output/result.json` 都存在且状态诚实：partial 不冒充 complete。
- 预算台账：逐阶段记录耗时与计数，超阈值即告警。

**边界（不做什么）**：

- 不负责事实核验、受众适配、叙事线设计（其他 Skill 的重心），本 Skill 只管运行层。
- 不调用第三方包、不联网；所有脚本仅 Python 3 标准库。
- 不预制答案：示例全部标注"合成示例"，result.json 由管线真实生成。
- 冲突检测是保守启发式：宁可误报列入人工确认，不静默放过。

## 运行契约

### 目录契约

| 路径 | 性质 | 说明 |
| --- | --- | --- |
| `/input/case.json` | 只读 | 含 `case_id`、`output_contract`、可能的 `inputs` 引用 |
| `/input/task.md` | 只读 | 任务书；可能含字数上限与路径引用 |
| `/app/work` | 可写 | 中间产物、`checkpoint.json`、`logs/` |
| `/app/output` | 可写 | 最终产物；`result.json` 必须落在这里 |

### result.json 契约

必须含 `case_id` 与 `case.json` 自带 `output_contract` 的全部字段。

**诚实 partial：status 三态判定规则（写死，不得绕过）**

- `complete`：当且仅当 ① `output_contract` 全部必填字段非空（空字符串/空数组/`null` 均为空；数字 0 是合法值）；② `limitations` 为空数组；③ 所有产物路径字段指向的文件真实存在。三条缺一即不得标 complete。
- `partial`：已有可交付内容，但上述任一条不满足。剩余缺口必须逐项写入 `limitations`，禁止留空数组冒充。
- `failed`：管线在任何阶段崩溃且无可用产物，或存在 halt 级异常。必须附 `failure.stage` 与 `failure.reason`。

由 `scripts/result_guard.py finalize` 机械执行上述规则；人工不得直接手改 status。

## 标准流程

`$SK` 代指 `/skills/weekly-skill`；定位失败时用 find 兜底：

```bash
SK=${SK:-/skills/weekly-skill}
if [ ! -f "$SK/scripts/run_pipeline.py" ]; then
  RP=$(find / -maxdepth 6 -name run_pipeline.py 2>/dev/null | head -n1)
  SK=$(dirname "$(dirname "$RP")")
fi
mkdir -p /app/work /app/output

# 1) 输入异常分流（先于一切写作）。退出码 2 = 存在 halt 项，停管线只交 partial
python3 "$SK/scripts/anomaly_triage.py" \
  --case /input/case.json --task /input/task.md \
  --indir /input --outdir /app/output
TRIAGE_RC=$?

# 2) 保底 result.json（任何时刻存在诚实 partial）
python3 "$SK/scripts/result_guard.py" init --case /input/case.json --out /app/output \
  --gap "（按 anomaly_register 逐条抄写 mark-gap 缺口）"

# 3) 分阶段执行（pipeline_plan.json 按案例编写；阶段命令为真实 subprocess）
python3 "$SK/scripts/run_pipeline.py" --plan /app/work/pipeline_plan.json --root /app/work
#    中断/崩溃后：python3 "$SK/scripts/run_pipeline.py" --plan ... --root ... --resume

# 4) 定稿（complete / partial / failed 由校验决定，不由意愿决定）
python3 "$SK/scripts/result_guard.py" finalize \
  --result /app/output/result.json --outdir /app/output --case /input/case.json
```

退出码约定：`anomaly_triage.py` 0=无 halt，2=有 halt，1=运行错误；
`run_pipeline.py` 0=全部成功，8=阶段失败（checkpoint 已保留），1=运行错误；
`result_guard.py` 0=命令成功（含判为 partial/failed），9=操作失败。

## 异常分类与处置表

| kind | 证据 | disposition | 对 result.json 的影响 |
| --- | --- | --- | --- |
| `missing_input` | case/task 引用的路径不存在或为 0 字节 | 个别缺失→`mark-gap`；全部文本输入缺失→`halt` | mark-gap：缺口写入 limitations，相关字段留空；halt：status=failed |
| `conflict` | 同一指标锚点（±10 字符窗口、公共子串≥4 字归并）跨文件取值不同 | `mark-gap` | 冲突数值一律不得写入交付物，limitations 注明"待人工确认口径" |
| `confidentiality` | 命中 保密/机密/confidential/未发表/embargo/内部资料/不得外传 | `proceed`（仅本地处理） | limitations 写入"仅本地处理、禁止外发"限制；不阻断本地管线 |
| `length_conflict` | task 字数上限 < 源文关键信息点×25 字的下限估计 | `mark-gap` | limitations 声明覆盖范围删减；禁止超字数硬塞 |

完整分类学见 `references/anomaly_taxonomy.md`。

## 最小合成示例说明

`examples/` 是可独立运行的合成示例（**非正式案例结果**）：

```bash
cd examples
python3 ../scripts/anomaly_triage.py --case case.json --task task.md --indir inputs --outdir /tmp/triage
python3 ../scripts/run_pipeline.py --plan pipeline_plan.json --root .   # 第一轮 → partial
rm work/stats.json
python3 ../scripts/run_pipeline.py --plan pipeline_plan.json --root . --resume  # 只重跑 stats
python3 ../scripts/run_pipeline.py --plan pipeline_plan_fixed.json --root .     # 修复后 → complete
```

`inputs/missing_table.csv` 被 case.json 引用但故意缺失；`main.md` 含"未发表数据"
字样；task.md 的能量密度口径（350）与 main.md（320）故意冲突；300 字上限与源文
信息量故意冲突。真实运行输出存于 `examples/expected/`（含 anomaly_register、
首轮 checkpoint、partial 与 complete 两版 result.json、resume 日志），复现命令与
结果见 `examples/README.md`。

## 局限

- 数值冲突检测为保守启发式：公共子串归并会漏掉换写法差异大的锚点，也会误报
  语境不同但字面相近的数值；所有冲突一律要求人工确认，不得自动采信任一方。
- 篇幅下限估计（关键信息点×25 字）只是量级判断，不能替代人工版面评估。
- 检查点按产物 sha256 判定重跑；若阶段命令含隐藏外部依赖（环境变量、网络），
  hash 不变不代表语义不变——计划内的命令应保持确定性。
- 预算台账只记录阶段数与耗时；模型请求数需由上层 harness 台账另行合并。
- 涉密识别仅限关键词标记；无标记的敏感内容不在本 Skill 防护范围内。
