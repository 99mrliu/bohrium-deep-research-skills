---
name: independent-oracle-lab
description: >-
  用事前冻结、带哈希的独立数学 Oracle、候选实跑和残差/缩放变形测试核验两个数值方法；区分数学真值、论文目标与复现状态，适用于真实 PDF、数据不全和两个候选实现的数值复现审计。
---

# Independent Oracle Lab

## 目的与边界

本 Skill 用于验证两个候选数值方法。核心证据是：**先从论文公式/定义写出事前 Oracle spec，再实际运行候选，随后用独立数学推导、高精度计算或确定性暴力搜索计算 expected，并在事前容差下比较。** 不通过重跑同一份代码、日志多数票、复现次数、两个候选互相同意或生成器共识来制造 Oracle。

本实现只支持 `references/oracles.md` 严格定义的两种 Oracle：

1. `quadratic_roots`：实根二次方程，Decimal 稳定解析公式、残差、Vieta 恒等式及非零系数共同缩放。
2. `brute_force_minimizer_1d`：闭区间上低阶到高阶系数表示的一元多项式，确定性均匀网格和局部细化。它是“已采样最佳值”，不是通用连续全局最优证明。

不宣称支持任意方程、任意 Python 表达式、复根、多变量优化、一般矩阵问题或通用论文复现。论文表图、原始数据和作者仓库缺失时，明确列出缺口；绝不补造。

## 强制工作流

### 1. 核查材料，禁止混同来源

- 正式任务从只读 `/input/case.json`、`/input/task.md`、真实 PDF 和两个候选的**实际入口**开始。阅读论文相关公式、变量定义、定义域、精度、表图目标与实验条件。
- 不假定候选叫 `main.py`、`solution.py`，不假定 `--input`、固定类名或固定 CLI。检查任务与源码后，把实际 argv 显式写入 spec；argv 数组直接执行，不经过 shell。
- 区分论文作者代码、组织方适配代码和合成候选。合成组织方代码只能标为测试夹具，不能写成作者方法。
- 若没有原始数据、环境参数或作者仓库，记入 `result.json.uncertainty`，不要用合成材料替代正式缺失材料。

### 2. 事前写 Oracle spec 并冻结

在 `/app/work/oracle_spec.json` 写信封结构：顶层只有 `spec_sha256` 和 `spec`。哈希是 `spec` 对象按 UTF-8、`sort_keys=true`、紧凑分隔符、`ensure_ascii=false` 规范序列化后的 SHA-256；运行器在任何候选启动前验证它。所有误差容差、缩放因子、网格参数和精度都必须在 spec 内，因而被哈希冻结。发现 spec 错了就停止、解释并另存版本；不能看到候选结果后静默改容差。

从论文独立提取：

- 数学定义和独立 expected 算法，而不是某候选源码的转写；
- `paper_target`：从论文表/图/文本读取的目标，允许且必须为 `null`（当未提供时）；
- Oracle 类型、参数、容差与变形计划；
- 两个候选各自的唯一 `id`、完整 `argv`、相对/绝对 `cwd`、独立 timeout、输出模式；
- `evaluation_mode: "synthetic"` 仅用于本夹具；正式任务省略或用 `"formal"`。

`paper_target` **绝不参与 expected 计算**。Oracle 数学结果与论文目标分栏比较；若两者不一致，`paper_vs_oracle.status` 为 `mismatched`，不得把 Oracle 真值篡改成论文值，也不得自动判候选错。论文目标缺失只表示 `not_provided`。

可用占位符只有 `{spec_dir}`、`{work_dir}`、`{output_dir}`、`{json_out}`、`{a}`、`{b}`、`{c}`、`{scale}`。二次方程缩放试验会替换系数；占位符不是候选发现机制，候选程序及参数必须已经在 argv 中明确指定。详见 `references/spec_and_contract.md`。

先在本地 `validate`，哈希不通过时退出码为 2，不能启动候选：

```bash
python3 /app/work/skill/scripts/oracle_lab.py validate \
  --spec /app/work/oracle_spec.json
```

本 bundle 的实际路径未必是 `/app/work/skill`；上式仅表示部署后的命令，应换成实际安装路径。标准库 Python 3.10+ 即可，无第三方依赖。

### 3. 实跑两个候选，隔离失败

正式平台默认命令：

```bash
python3 /actual/skill/path/scripts/oracle_lab.py run \
  --spec /app/work/oracle_spec.json \
  --case /input/case.json \
  --work-dir /app/work \
  --output-dir /app/output \
  --budget-seconds 900
```

- `/input` 只读；中间 JSON/日志及候选临时输出放 `/app/work`；最终 `oracle_report.json`、`oracle_report.md`、`result.json` 放 `/app/output`。
- 保留每次实际渲染后的 argv、cwd、stdout、stderr、退出码、耗时、timeout、JSON 解析状态和解析错误。不会把“退出码 0”或“JSON 可解析”当作数值正确。
- `last_json_line` 只读最后一个非空 stdout 行；`json_file` 读取 argv/spec 明示的路径。缺输出、非 UTF-8 文件、无效 JSON、非有限数值均诚实记录。
- 某个候选启动失败、超时、非零退出、解析失败或数值失败，均记录后继续另一个。运行器每完成一个候选就落盘 partial 证据；全局预算封顶 900 秒，剩余时间会限制后续 timeout。
- 整体运行器退出码 0 表示“审计流程完成并写报告”，不表示所有候选通过；spec 非法为 2，运行器自身异常为 1。

### 4. 判定并做论文层复现

分别回答：

1. **候选 vs Oracle 数学结果**：expected、绝对误差、相对容差界限、残差/恒等式、缩放结果。
2. **论文目标 vs Oracle 数学结果**：`matched`、`mismatched` 或 `not_provided`。
3. **候选 vs 论文表图**：仍须逐项比较真实论文目标与候选结果；Oracle 一致不等于论文复现。
4. **正式任务完整性**：材料和环境参数、两个候选实跑、论文表图比较、差异归因都不可省略。候选数值差异之后，再从公式实现、参数、数据、环境、随机性和论文目标差异作有证据的归因；不能把“观察到误差”冒充“已定位根因”。

`_witness` 不完整时，运行器保持 `partial`。即使两个候选数学检查通过，若没有正式表图比较与差异归因，也不能宣称论文复现完成。论文与数学真值不一致必须单列为论文-数学差异，不可隐藏或投票消解；`paper_vs_oracle` 或 `candidate_vs_paper` 的 `mismatched` 本身不触发执行失败，也不阻止其他证据齐全时判定 `success`。

## 平台输出契约

- **先交 partial，后补全，不超过 900 秒。** 缺失材料不能阻止写出已有执行证据。
- `result.json` 顶层 `status` 只能为 `success`、`partial`、`unable`、`refused`。所有候选实跑及所需证据齐全才为 `success`；候选失败、合成夹具、来源缺失、witness 不完整或契约字段未填证据均为 `partial`；`case_id` 不可用或致命执行错误导致任务无法执行为 `unable`。执行流程完成度另记 `oracle_report.json.completion_status`（`complete`/`partial`），不得把执行完成误写成任务成功。
- `result.json` 顶层必须有 `case_id`、`status`、`sources`、`uncertainty`、`change_records`，并将 `/input/case.json` 的 `output_contract` **每一个字段原样平铺到顶层**。不要把契约字段塞进 `output_contract` 或其他嵌套对象；契约要求上述五个标准字段时直接复用，不新增包装层。
- 支持 `output_contract` 为字段字典、字符串列表、`fields`/`required_fields` 列表或字段 mapping，以及 JSON Schema 的 `properties`/`required`；含 `name`/`key` 的字段项也能识别。已知字段由运行器填充，`spec.contract_values` 可提供有案件证据的覆盖值；未知字段明确标为未由 Oracle 运行器填妥并导致 `partial`，不能伪造内容。
- `sources` 指明 case/任务/论文材料/候选源码路径及作者代码标记；`uncertainty` 记录数据、仓库、参数、PDF 提取与适用范围缺口；`change_records` 记录执行和产物且标明未改候选源码。
- 运行器输出是独立数值审计结果，不是自动替代正式科研报告。正式 agent 必须完成case要求的材料盘点、两候选与论文表图比较和差异归因，并用证据填充所有契约字段。

## 文件与示例

- `scripts/oracle_lab.py`：spec 校验、候选隔离执行、两类 Oracle、比较、报告及内置自检。
- `references/oracles.md`：精确定义、输入输出、容差、残差和限制。
- `references/spec_and_contract.md`：spec、路径、输出契约与正式交付要求。
- `examples/`：两个不同 Python 候选（一个稳定通过，一个真实把顶点重复为两根）、合成文本材料、case/task、已冻结 spec 与预期结果。

实际验证示例（显式指定隔离目录）：

```bash
python3 scripts/oracle_lab.py self-test
python3 -m unittest discover -s tests -v
bash examples/run_example.sh /app/work/example-output /app/work/example-intermediate
```

`run_example.sh` 要求传 `OUTPUT_DIR WORK_DIR`，不会猜测路径。预期失败候选先失败、通过候选仍继续，最终诚实为 `partial`，详见 `examples/expected.txt`。
