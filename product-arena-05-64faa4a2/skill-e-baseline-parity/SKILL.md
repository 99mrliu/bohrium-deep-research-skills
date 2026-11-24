---
name: baseline-parity
description: 工程化“方法与实验”章节中的对照实验小节——建基线台账、核验同预算与统计协议、校验比较性论断，保证“优于基线”是身份明确、同预算、同划分、统计写清的可比结论。
---

# baseline-parity：对照实验与统计协议的可比性工程

## 1. 用途

本 Skill 面向科研写作中“方法与实验章节”的**对照实验小节**。其核心命题是：
“优于基线”只有在**基线身份明确、同预算、同数据划分、指标与统计方式写清**时，
才构成可比结论。本 Skill 将该命题工程化为四步流水线：

1. **基线台账**：从材料中识别每个基线的名称、版本、来源（自复现 / 原报 / 未知），
   原报值必须标引文并注明“非同等条件”；
2. **同预算核验**：训练步数 / epoch / 数据量 / 调参预算在对照组间是否一致，
   不一致必须显式声明；
3. **指标与统计协议**：主指标定义、重复次数、均值±标准差、显著性检验方法与置信水平，
   缺一项即记为缺口；
4. **论断校验**：章节中“优于 / 超过 / 相当 / outperform / comparable”类比较级论断，
   必须有指标＋数值＋统计依据支撑，否则降级为描述性陈述或标注 `[待确认]`。

最终产出对照实验小节骨架与**可比性矩阵表**（行＝对照项，列＝基线A/B/本文，
单元格取值 同 / 异 / 未知），并保证所有论断可追溯至材料中的 file:line 证据。

## 2. 运行时契约（必须遵守）

1. **先读输入再动笔**：写作前必须读取 `/input/case.json` 与 `/input/task.md` 的
   实际内容，不得凭任务名臆测；材料目录中的配置、日志、代码、草稿、PDF 提取文本
   均为证据来源。
2. **工作目录**：中间产物写入 `/app/work`（台账、核验报告、论断报告、章节草稿）。
3. **产物目录**：最终产物写入 `/app/output`，包括章节正文与 `result.json`。
4. **result.json**：必须包含 `case_id` 与 `output_contract` 的**全部字段**；
   字段值缺失时用显式的空值或“未知”，不得省略字段。
5. **诚实状态**：`result.json` 中如实填写完成状态；未完成的项写入 `partial`，
   并说明原因；不得将未完成包装为完成。
6. **尽早保存**：每完成一个流水线阶段（台账 / 核验 / 小节草稿 / 论断校验 /
   装配）立即把当前产物落盘到 `/app/work`，最终版本及时复制到 `/app/output`，
   防止预算耗尽导致产物丢失。
7. **来源定位**：章节中的每个关键事实（基线身份、数值、预算取值）须在草稿或
   工作笔记中保留 `file:line` 定位；脚本产出的台账与报告自带证据字段，直接引用。
8. **修改记录**：对材料或草稿的任何改写（尤其是论断降级改写）记入
   `/app/work/change_log.md`：原文、改后、理由、依据文件。
9. **不确定性**：凡证据不足的判断（如基线版本未知、预算未知）在文中与
   `result.json` 中标注“未知 / 不确定”，禁止以猜测填充。
10. **人工确认项**：所有 `[待确认]` 标注、原报值的使用、`未知` 单元格，
    汇总为人工确认项清单写入 `result.json`。
11. **章节覆盖六要素**：方法与实验章节必须覆盖——
    ①步骤（方法流程与实验流程）；②实验设置（数据、模型、训练配置）；
    ③参数与来源（每个超参的取值与出处）；④数据集与划分（train/val/test 口径）；
    ⑤对照（本 Skill 的重心：基线台账＋同预算核验＋可比性矩阵）；
    ⑥复现与限制（随机种子、代码/配置位置、已知不可比之处与局限）。

## 3. 环境与工具约束

- 三个脚本均为**纯 Python 标准库**实现（`argparse/json/os/re/sys`），
  **确定性输出**（文件遍历排序、结果排序），**无网络访问**；
- 运行环境仅需 `python3`（≥3.6），无需安装任何依赖；
- 脚本只读取文本类材料（.txt/.md/.log/.yaml/.yml/.json/.csv）；
  PDF 等其他格式须先用环境已有工具提取文本后再作为输入。

## 4. 调用步骤

设材料目录为 `$MAT`（从 `/input/case.json` 与 `/input/task.md` 中解析得到），
工作目录 `/app/work`，产物目录 `/app/output`。

### ① 建基线台账

```bash
python3 /skills/weekly-skill/scripts/baseline_mine.py \
  --input "$MAT" --out /app/work/baselines
```

- 产出 `baselines.json` / `baselines.md`：每个基线的名称、版本、来源类型
  （自复现 / 原报 / 未知）、引用标记、关联指标与数值、证据 `file:line`；
- 模型必须**逐条人工复核**脚本判定：来源类型为启发式结果，
  尤其是“未知”项要回到材料原文确认；
- 原报值基线（`source_type=原报`）在章节中必须带引文并注明“非同等条件”。

### ② 同预算与统计协议核验

```bash
python3 /skills/weekly-skill/scripts/parity_check.py \
  --input "$MAT" --draft /app/work/section_draft.md --out /app/work/parity
```

（草稿尚不存在时可省略 `--draft`，写完初稿后再跑一次。）

- 产出 `parity.json` / `parity.md`：各 run 的 epochs/steps/数据量/调参预算汇总表、
  **parity 违规清单**（预算不一致或预算未知）、**统计协议缺口清单**
  （重复次数 / 均值±标准差 / 显著性检验，缺一项列一项）；
- 每一条违规必须在章节中显式声明差异及理由；每一个缺口要么补齐、
  要么声明缺口并降级相关论断。

### ③ 撰写对照实验小节

依据 `references/comparability_spec.md` 第 6 节的骨架撰写：

1. 对照设置：基线清单（身份五要素）与选择理由；
2. 可比性声明：同预算核验结论＋可比性矩阵表（模板见规范第 5 节，
   单元格只能填 同 / 异 / 未知，无证据一律填“未知”）；
3. 结果：主指标表，自复现与原报分行，注明重复次数与 mean±std；
4. 统计检验：检验方法与置信水平；
5. 复现与限制：种子、配置位置、已知不可比之处。

措辞纪律遵循 `references/claim_discipline.md`：无同预算不称“公平对比”，
无重复实验不称“显著”，原报值不进入排名断言。

### ④ 校验比较性论断

```bash
python3 /skills/weekly-skill/scripts/claim_check.py \
  --draft /app/work/section_draft.md \
  --input "$MAT" --baselines /app/work/baselines/baselines.json \
  --out /app/work/claims
```

- 产出 `claims_report.json` / `claims_report.md`：逐句列出比较级论断的
  支撑状态（指标＋数值 / 数值可定位 / 统计支撑）、问题、备注与改写建议；
- **退出码非零表示存在无支撑论断**，必须逐条处置：
  能补证据则补证据保留论断；否则按建议降级为描述性写法或标注 `[待确认]`；
- 处置后**重新运行本步直至退出码为 0**，或把剩余 `[待确认]` 项
  全部转入人工确认项清单。

### ⑤ 装配 result.json

1. 把最终章节复制到 `/app/output`；
2. 按 `/input/case.json` 的 `output_contract` 装配 `/app/output/result.json`：
   填入 `case_id` 与全部契约字段；
3. 写入诚实状态与 `partial`（如有），附：
   - 来源定位表（关键事实 → file:line）；
   - 修改记录（引用 `/app/work/change_log.md`）；
   - 不确定性清单（所有“未知/不确定”项）；
   - 人工确认项清单（`[待确认]`、原报值使用、可比性矩阵中的“未知”单元格）。

### 脚本接口速查

| 脚本 | 必选参数 | 可选参数 | 产物 | 退出码 |
|---|---|---|---|---|
| `scripts/baseline_mine.py` | `--input`（可重复）、`--out` | `--max-evidence` | `baselines.json/md` | 恒 0 |
| `scripts/parity_check.py` | `--input`（可重复）、`--out` | `--draft` | `parity.json/md` | 恒 0 |
| `scripts/claim_check.py` | `--draft`、`--out` | `--input`（可重复）、`--baselines` | `claims_report.json/md` | 有无支撑论断时为 1 |

通用约定：`--input` 接受目录或单文件，目录递归遍历且顺序确定（排序）；
扫描扩展名为 `.txt/.md/.log/.yaml/.yml/.json/.csv`；所有产物为 UTF-8；
脚本判定均为启发式，结论以模型回到原文复核为准。

### 产物组织建议

```
/app/work/
  baselines/baselines.json, baselines.md     # 步骤①
  parity/parity.json, parity.md              # 步骤②
  section_draft.md                           # 步骤③ 小节草稿（含 file:line 证据注记）
  claims/claims_report.json, claims_report.md# 步骤④
  change_log.md                              # 修改记录
/app/output/
  <章节正文>.md                               # 定稿
  result.json                                # case_id + output_contract 全字段
```

## 5. 异常处理

| 异常 | 处置 |
|---|---|
| 材料目录不存在或为空 | 在 result.json 中如实报告 `partial`，说明缺材料，不臆造基线与数值 |
| 材料无可解析文本（仅 PDF 等） | 先用环境已有工具提取文本到 `/app/work`，再以提取文本为输入；提取失败则记 partial |
| 脚本运行报错 | 记录 stderr 到 change_log，改用人工阅读材料完成对应步骤，不得跳过该步骤的产出 |
| 台账识别为 0 个基线 | 人工通读材料确认；确认无基线则进入“无对照实验”边界流程（第 7 节） |
| parity_check 发现预算未知 | 回到材料补齐；补不齐则在可比性矩阵填“未知”并降级相关论断 |
| claim_check 退出码非零且无法补证据 | 按建议改写为描述句或标 `[待确认]`，全部列入人工确认项 |
| 预算（请求数/时间）将尽 | 立即把当前最好版本落盘 `/app/output` 并装配 result.json（标 partial），保证有产物 |

## 6. 合成最小示例

`examples/` 内含一套**合成示例（非正式案例结果）**：

- `examples/case/`：`config_ours.yaml`（本文，epochs=200）、
  `config_base.yaml`（基线 ResNet-50，epochs=50，故意不一致）、
  `results.log`（两个 run 各一条指标，单次运行）、
  `refs.md`（VGG-16 [1] 原报值 71.3，注明非同等条件）、
  `draft.md`（含无支撑论断“我们的方法显著优于所有基线”）；
- 一键运行：`bash examples/run_example.sh`，产物写入 `examples/expected/`；
- 预期：`baseline_mine` 识别 ResNet-50（自复现）与 VGG-16（原报，引用 [1]）；
  `parity_check` 报出 epochs 预算不一致与统计协议三缺口；
  `claim_check` 抓出无支撑论断并以退出码 1 结束（脚本捕获该码，整体正常退出）。

## 7. 边界：材料中没有对照实验

当材料中不存在任何基线 / 对照设置时，**不得编造对照实验**。按以下方式诚实声明：

1. 对照实验小节照常保留，写明“本工作材料中未包含对照实验设置”，
   并在可比性声明处填 `not_applicable`；
2. 可比性矩阵表退化为单列“本文”，对照项取值按材料实填（无证据填“未知”）；
3. `result.json` 中：对照相关字段填 `not_applicable` 并附原因说明，
   状态标 `partial`（若契约要求对照而材料不支持）；
4. 把“是否需要补充对照实验”列入人工确认项；
5. 方法与实验章节其余五要素（步骤、设置、参数与来源、数据与划分、
   复现与限制）仍须按材料完整撰写，不受对照缺失影响。

## 8. 参考文件

- `references/comparability_spec.md`：基线身份五要素、同预算定义、
  原报值引用规则、统计协议最低要求、可比性矩阵表模板、小节骨架；
- `references/claim_discipline.md`：论断-证据配对、无同预算时的措辞、
  常见夸大模式与降级改写示例、强措辞门槛。

## 9. 预算与节奏建议（64 次请求 / 900 秒）

1. 读输入与浏览材料（少量请求）；
2. 步骤①②各跑一次（无模型请求），复核结果；
3. 撰写小节初稿并落盘；
4. 步骤④校验 → 改写 → 复校（循环控制在 2～3 轮）；
5. 装配 result.json 并做最终一致性检查；
6. 全程遵守“尽早保存”，每阶段结束即落盘。
