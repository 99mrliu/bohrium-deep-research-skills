---
name: rng-determinism-lab
description: 运行环境与随机性取证（execution determinism forensics）。当评测题目要求实际运行候选数值方法代码、核对指标并归因与论文的差异时触发；核心主张是在任何比较之前先证明"同一份代码在同一台机器上重跑得到同一个数"。提供零运行 AST 静态审计（import/随机调用点/播种点/非确定性风险逐行定位）、固定 PYTHONHASHSEED 下的受控重放（N 次重跑，机械判定 identical / numerically_stable / unstable，产物文件 sha256 对比）、以及环境快照与可重建说明。只产出 determinism 证据供下游使用，不做与论文数值的比较判定。
---

# rng-determinism-lab：运行环境与随机性取证

## 用途与适用条件

本 Skill 只解决一个问题：**"结果对不上"在归因之前，先回答"同一份代码在这台机器上
重跑是否得到同一个数"。** 如果同机重跑都不确定，任何与论文数值的比较都没有意义。

适用条件（触发场景）：

- 题目给出两份（或多份）候选数值方法代码，要求实际运行、核对指标、并归因与论文的
  差异（"参数/代码/指标验算与差异归因"子场景）；
- 需要判断差异究竟来自实现、参数、数据，还是单纯来自**未控制的随机性/环境**；
- 需要为下游比较步骤提供可信的执行确定性证据与环境可重建说明。

不适用：与论文数值的统计比较、显著性判定本身（那是下游步骤，本 Skill 只交付证据）。

## 背景与评测契约（必须遵守）

- 平台把本 Skill 安装到 `/skills/weekly-skill`，由官方 DeepSeek Harness 跑固定案例。
- 每案例输入在 `/input/case.json` 与 `/input/task.md`；`case.json` 含 `case_id` 与
  `output_contract` 字段清单。材料按题目提供（真实 PDF 论文；两份候选数值方法代码，
  需实际运行核对指标）。**原始数据/作者仓库缺失是预期情况，要显式登记，不得编造。**
- 工作在 `/app/work`，最终产物在 `/app/output`，必须含 `result.json`（含 `case_id`
  与 `output_contract` 全部字段、诚实 `status: success/partial/unable/refused`、
  来源定位、不确定性、变更记录）。
- 预算约 64 次模型请求 / 900 秒：命令一次想清楚再跑，失败先读报错再重试。
- **组织方合成代码 ≠ 作者原代码**；在合成数据上跑通不能写成"论文数值复现"。
- 禁止编造数据；一切数字必须来自真实文件的读取或真实命令的输出。

## 核心思想

1. **先同机确定，再跨机/对论文比较。** 确定性证据的层级：同机同环境重放
   （本 Skill）→ 同机改环境重放 → 跨机 → 对论文。第一层不过关，后面全是空谈。
2. **随机方法必须显式播种，并把种子写进参数表。** 种子按三分类登记：论文明示 /
   代码默认 / 自行设定（见 `references/determinism.md` 第 2 节）。
3. **机械判定，不做统计推断。** identical / numerically_stable / unstable 是字节级与
   数值序列级的机械比较结论，本身不是"复现成功"或"实现错误"的结论。

## 铁律

- **读真实文件**：所有结论必须来自对 `/input` 真实材料的读取与真实命令的输出；
  禁止凭记忆或猜测填写任何数值。
- **不改原代码**：候选脚本原样运行。发现未播种等问题，记录事实；如需固定种子重放，
  用运行侧手段（环境变量、包装命令），并在变更记录中写明。擅自改码 = 失去比较基准。
- **失败/超时也是观测**：非零退出码、spawn_error、timeout 全部如实写入报告，
  不粉饰、不丢弃、不重复硬跑碰运气。
- **result.json 全字段诚实**：`output_contract` 的每个字段都要填；做不到的字段写
  `unable`/说明原因，status 用 `partial` 而不是硬凑 `success`。
- **预算纪律**：约 64 次模型请求 / 900 秒。静态审计（零运行）优先于重放；
  重放次数默认 3 次，不超过 5 次；超时参数显式给，不让任何命令裸奔。

## 逐条命令流程

下文 `$SKILL` 指代本技能目录（评测时即 `/skills/weekly-skill`）。建议在 `/app/work`
下建 `determinism/` 子目录存放全部证据。

```bash
SKILL=/skills/weekly-skill
mkdir -p /app/work/determinism

# 0) 读输入：case.json（case_id、output_contract 字段清单）、task.md、候选代码清单
cat /input/case.json
cat /input/task.md

# 1) 零运行静态审计（每个候选脚本一份；非 .py 会得到 not_applicable，退出码 2）
python3 $SKILL/scripts/code_audit.py /input/candidate_a.py \
    > /app/work/determinism/code_audit_candidate_a.json
echo "exit=$?"   # 0=审计完成（含 parse_error），2=非 .py（not_applicable）

# 2) 环境快照（在运行候选之前做；--imports 按代码实际依赖填写）
python3 $SKILL/scripts/env_snapshot.py \
    --out /app/work/determinism/env --imports numpy,scipy,torch

# 3) 受控重放：同一命令固定 PYTHONHASHSEED=0 跑 N=3 次
#    注意：重放以 run_<i>/ 为 cwd，脚本路径用绝对路径；--artifact 用相对 run 目录的路径
python3 $SKILL/scripts/replay.py --name candidate_a --runs 3 --timeout 120 \
    --out /app/work/determinism/replay_candidate_a \
    -- python3 /input/candidate_a.py
# 若脚本会写结果文件（如 metrics.json 写在 cwd），声明 artifact 做逐次 sha256 对比：
python3 $SKILL/scripts/replay.py --name candidate_b --runs 3 --timeout 120 \
    --artifact metrics.json \
    --out /app/work/determinism/replay_candidate_b \
    -- python3 /input/candidate_b.py

# 4) 读报告：determinism_report.json 的 verdict 字段
#    identical / numerically_stable -> 可进入下游比较
#    unstable -> 先按 references/determinism.md 固定随机性来源再重放
#    spawn_error -> 命令本身无法启动，属环境/材料问题，如实登记

# 5) （仅当 unstable 且候选支持种子参数时）固定种子重放一次作对照，种子按三分类登记
python3 $SKILL/scripts/replay.py --name candidate_b_seeded --runs 3 --timeout 120 \
    --artifact metrics.json \
    --out /app/work/determinism/replay_candidate_b_seeded \
    -- python3 /input/candidate_b.py --seed 0
```

## 输入与输出

输入：

- `/input/case.json`、`/input/task.md`：案例契约（case_id、output_contract 字段）。
- `/input/` 下的候选数值方法代码与题目提供的论文 PDF / 数据（缺失属预期，须登记）。

输出（全部放 `/app/output`，中间产物可留 `/app/work`）：

- `result.json`：含 `case_id` 与 `output_contract` 全部字段、`status`
  （success/partial/unable/refused）、来源定位（文件+行号/命令+报告路径）、
  不确定性说明、变更记录（本 Skill 正常应为"未修改任何候选代码"）。
- determinism 证据：`code_audit_*.json`、`replay_*/determinism_report.json`、
  `replay_*/report.md`、`env/env.json`、`env/rebuild.md`。

## 异常处理表

| 情形 | 处理 |
|------|------|
| 候选脚本不是 Python | `code_audit.py` 退出码 2、输出 `not_applicable`；环境快照与受控重放**仍可做**，在 result.json 注明静态审计不适用 |
| 候选不支持种子参数 | 只记录"未播种/种子不可控"的事实与证据，**不得擅自改码加种子**；可在变更记录中说明"如需固定须改码，未执行" |
| 重放判 unstable | 建议固定种子/PYTHONHASHSEED/线程数后重放（候选支持时），并**如实写入不稳定事实**；同机不稳定≠实现错误，但必须先固定再比较 |
| 命令不存在/无法启动 | replay 记 `spawn_error`，不中断整体报告；登记为环境/材料问题 |
| 运行超时 | replay 杀进程组并记 `timeout=true`，属有效观测；必要时调大 --timeout 重试一次并登记 |
| 依赖缺失（import 失败） | 如实记录退出码与 stderr 关键行；不擅自安装、不猜测结果；env_snapshot 中对应包为 `not_installed` |
| 脚本语法错误 | code_audit 输出 `status=parse_error` 的结构化 JSON（含行号）；重放结果照实记录 |
| 原始数据/作者仓库缺失 | 显式登记为预期情况；合成数据上的通过不得写成论文数值复现 |

## 运行契约

- 输入只读：`/input`；工作区：`/app/work`；最终产物：`/app/output`。
- `/app/output/result.json` 必须含 `case_id` 与 `output_contract` 列出的**全部字段**，
  缺字段即不合规；每个字段附来源定位与不确定性。
- 诚实优先：做不完的字段写 `unable` + 原因，整体 `status` 用 `partial`；
  本 Skill 的证据只支持"执行确定性"层面的结论，越界结论（如"复现了论文表 3"）
  禁止写入。
- 预算：约 64 次模型请求 / 900 秒；重放默认 3 次，静态审计先行。

## 最小合成示例

`examples/` 内含**合成示例（synthetic），非正式案例结果**：

```bash
bash $SKILL/examples/run_example.sh /app/work/determinism/example
```

依次执行：code_audit 两个合成脚本 → replay 各 3 次 → env_snapshot。
预期（`examples/expected/` 有预期副本）：

- `method_stable.py`（纯确定计算）：replay 判 `identical` 或 `numerically_stable`；
- `method_unseeded.py`（用 `random` 不播种，写 `result_unseeded.txt`）：
  replay 判 `unstable`，产物 sha256 各次不同；code_audit 报"未播种 RNG"告警并给行号。

## 限制与自查

限制：

- 仅标准库、纯文本输出；code_audit 是静态分析，看不到动态 import、`eval`、
  C 扩展内部随机性；审计通过 ≠ 确定，最终以重放为准。
- replay 的数值抽取是正则机械抽取，会把行号/计数器等非指标数字算进去；
  unstable 分叉索引指向抽取序列位置，需人工核对语义。
- 本 Skill 不判定与论文的数值一致性，不产出复现成功结论。

自查清单（交付前逐项打勾）：

- [ ] 每个候选脚本都有 code_audit 输出（或 not_applicable 记录）；
- [ ] 每个候选脚本都有 ≥3 次受控重放报告，verdict 已读并写入 result.json；
- [ ] unstable 的候选已按 references/determinism.md 排查并记录固定尝试或不可固定原因；
- [ ] env.json / rebuild.md 已生成，关键环境变量与依赖版本已登记；
- [ ] result.json 含 case_id 与 output_contract 全部字段，status 诚实，变更记录为
      "未修改任何候选代码"（或如实列出经允许的运行侧固定手段）；
- [ ] 未编造任何数据；所有数值可回溯到具体文件或命令输出。
