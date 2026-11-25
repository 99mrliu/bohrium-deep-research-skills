---
name: dataset-provenance-lab
description: >-
  核验论文复现与方法验证中上游数据身份、版本、SHA256、schema、target/features 和 train/test 可比性；当任务给出真实论文 PDF、/input/case.json、/input/task.md、两个候选数值方法，或要求检查精确重复、feature-only 交叉重复及论文 n_rows/n_features/split 声明时触发。非触发：通用科研全流程台账、文献综述、与数据无关的代码调试、纯图像生成、只做数值方法排行榜，或把统计异常直接判定为合成数据/标签泄露。
---

# Dataset Provenance Lab

## 目的与边界

本 Skill 只处理**论文复现/方法验证的上游数据与切分真实性、身份和可比性**。它不是一个通用实验台账，也不替两个候选方法选优。核心问题是：实际拿到的字节是什么、字段如何定义、切分如何对应、哪些论文数字能由给定证据核验，以及两个方法是否确实在可比数据上运行。

正式场景通常是 `/input/case.json`、`/input/task.md`、真实论文 PDF（没有预抽取答案层）和两个候选数值方法。组织方合成试验**不是**作者原代码、物理实验或全量 PMLB；不得改写其身份。原始数据或原仓库缺失必须保留为显式范围限制，不能静默补全、猜测 URL、把替代数据称为原始数据，或宣称已复现原作者实验。

不假定存在固定数据集文件名。文件名、角色、target、features、split 和论文证据只能来自实际 case、task、manifest、PDF 与数据内容；每次先枚举输入再决定路径。

## 平台运行契约

1. 只读 `/input`：读取实际存在的 `case.json`、`task.md`、PDF 和由 case/task/manifest 指向的数据。不要寻找或读取凭据。
2. 中间文件写 `/app/work`，最终交付写 `/app/output`。推荐最终至少包括 `result.json`、`audit.json`、`report.md`；实际文件名若由合约指定，以合约为准。
3. `result.json` 的顶层必须有与输入完全一致的 `case_id`、合法的 `status`、`sources`、`uncertainty`、`change_records`，以及 case 的 `output_contract` 要求的**全部字段**。这些合约字段必须平铺在顶层；不得只放进嵌套的 `output_contract` 对象，也不要原样回显一个嵌套合约来冒充交付。
4. `status` 只能诚实使用 `success`、`partial`、`unable`、`refused`。未运行两个候选、缺关键原始数据、PDF 证据不足或比较未完成时不得写 `success`；可以交付有证据的 `partial`。拒绝或不支持的原因也要保留可审计结果。
5. `sources` 记录实际读取的文件/PDF/仓库标识及可用哈希；`uncertainty` 记录不可验证项与推断边界；`change_records` 记录清洗、类型转换、行列排除、重建切分等变更。未变更也要写空数组或说明，不可删除字段。
6. 总时限按 900 秒管理。**在接近 900 秒前**先保存合约完整的 `partial` 结果、已有 audit 和 report，再继续完善；发生超时风险时立即保存，不得只留下最终答案文本。

不要假定合同只有 `output_contract.required_fields`。审计器和校验器支持直接的字段数组/字段 mapping、`fields`/`required_fields` 容器，以及直接或位于 `schema`/`json_schema` 下的 JSON Schema `properties`/`required`。JSON Schema 的 `properties` 是全部声明字段，`required` 是必填子集；数组、直接 mapping 及只给一个 fields 容器的形状均视为全部必填。`case_id`、`status`、`sources`、`uncertainty`、`change_records` 可以本身列为合同字段，不算 collision，仍只保留一份标准顶层值；`output_contract` 不能作为答案字段。详细语法和校验命令见 [references/result-contract.md](references/result-contract.md)。

## 正式任务闭环

### 1. 固定问题、输入和时间点

- 读取 case/task，复制 `case_id`，按实际形状解析 `output_contract` 的全部声明字段和必填子集，记录开始时间。区分正式输入与示例。
- 枚举 PDF、数据、候选方法及环境；不得假定 `train.csv`、`test.csv` 或任何固定名称。
- 缺原始数据、仓库、代码或许可时明确记录“不可得/未提供”，不要根据统计形态推断来源。

### 2. 建立有来源的 manifest

以 [references/manifest.schema.json](references/manifest.schema.json) 为结构，在 `/app/work` 创建 manifest。每个实际文件记录稳定 `id`、显式相对/绝对 `path`、角色、SHA256、格式、列分隔符与编码。记录声明的版本和来源，不把“下载地址”误当作版本或真实性证明。

显式写出 target 列、features 列表、train/test 文件 ID；不要轻易把 ID、时间、split 标志或 target 当 feature。自动推断的类型只是观测，不能替代论文字段语义。原始文件保持只读，变更通过 `change_records` 追踪。

### 3. 从真实 PDF 核对论文声明

对论文的 `n_rows`、`n_features`、`split` 声明逐项记录：

- `page`：PDF 页码；如同时有印刷页码，可在报告补充，不能混淆；
- `quote`：人工从该页读取并逐字转录的原文，含足够上下文；
- `locator`：可重算该声明的文件 ID、feature 列表或 train/test 文件 ID；
- `expected`：论文声明的数值或 split 计数。

三者任一缺失，该声明必须标为 `unverifiable`，不能猜页码、补引文或仅凭数据反推论文原话。脚本只核对“记录的预期值”和实际数据是否一致，**不证明引文忠实、数据真实或来源属实**。真实 PDF 没有预抽取答案层时，agent 必须亲自阅读相应页面；不可把本 Skill 的合成示例当作 PDF 内容。

### 4. 运行数据审计

从包根目录可使用：

```bash
python3 scripts/audit_dataset.py \
  --manifest /app/work/manifest.json \
  --case /input/case.json \
  --task /input/task.md \
  --output-dir /app/output
```

输入输出均由参数显式指定，失败返回非零。工具生成 `audit.json`、`report.md`、`summary.txt` 和一个 `partial` 的 `result.json` 草稿。它只是审计起点，不会运行候选方法。草稿平铺全部声明字段；审计无法产生的字段使用 `{"status":"unavailable","reason":...,"completion_required":true}` 并在 `uncertainty` 留痕，不能把这些占位当成已完成。合同没有 `limitations` 时，报告仍使用 audit 的范围限制，不会崩溃。

审计包括：每文件 SHA256（声明值与实际值）、行列数、观测类型、逐列缺失、全行重复、target 分布、train/test 全行精确交叉重复，以及排除 target 后的 feature-only 精确交叉重复。完整定义见 [references/audit-rules.md](references/audit-rules.md)。

### 5. 解释异常但不越界

- 精确全行重复表示所选列值完全相同；feature-only 重复表示 features 相同，target 可以相同或不同。
- feature-only 交叉重复可能来自合法重复个体、离散特征空间、抽样或预处理；target 冲突是需要追查的线索，不是泄露证明。
- 缺失、异常分布、重复率或“过于整齐”的数字均不能自动证明数据是合成的，也不能自动证明标签泄露。标签泄露还需字段语义、采集时间、生成机制或代码证据。
- 不做未经证实的作者意图、物理来源或 PMLB 覆盖范围结论。缺原始数据时，把结论限定为“对本次提供文件的审计”。

### 6. 两个候选数值方法仍必须实际完成

数据审计**不能替代**正式任务的数值复现与方法验证。正式任务必须：

1. 实际运行两个候选，而非只阅读说明或引用论文数字；保留各自命令、退出状态、日志和输出。
2. 记录环境：Python/包版本、操作系统、可用硬件、BLAS/线程、随机种子、数据版本、候选版本及全部关键参数。
3. 在看到比较结果前写下事前容差、主要指标和可接受差异；不能事后调容差迎合候选。
4. 在相同审计后的数据/target/features/split 上比较预测或数值输出、指标、运行成本与稳定性。
5. 对差异做归因：区分数据身份/切分、实现、参数、随机性、数值精度和方法本身；证据不足时保留多种解释。

若时间不足，先保存含已完成候选原始结果的 `partial`，将未运行项和不可比原因写入 `uncertainty`/`limitations`。不得把数据审计的通过当作方法验证成功。图比较主题由其他 bundle 承担，本 Skill 不要求生成图。

### 7. 完成并校验交付

将候选运行、事前容差、比较和归因写入 `method_comparison`，按实际合同合并 audit 的 `data_identity`、`data_quality`、`split_audit`、`paper_claim_checks`，以及合同声明时的 `limitations`。用任务证据替换所有 `unavailable` 占位后再考虑提升状态；核查全部必填字段仍在顶层，再运行：

```bash
python3 scripts/check_result.py --case /input/case.json --result /app/output/result.json
```

校验器的退出码为 0 只表示结构检查通过，不表示科学结论正确。最终 `report.md` 应把数据事实、论文事实、运行事实和解释分开，并保留原始数据/仓库缺失造成的范围限制。

## 最小合成示例

`examples/` 是 **synthetic 合成示例，非正式案例、非作者原始数据、非真实论文、非物理实验、非 PMLB**。其中 train/test 故意有两个 feature-only 交叉重复，一个同时是全行重复，另一个 target 冲突。它没有两个候选方法，所以结果必须为 `partial`。

```bash
examples/run_example.sh /absolute/writable/verification-output
```

该命令真实运行审计、核对 `expected.txt`，并构造结构错误的 result 负例；负例如被校验器接受，示例脚本会失败。随后运行 `examples/test_output_contracts.py`，覆盖 list、字段 mapping、fields/required_fields、JSON Schema properties/required 的解析，以及 list/JSON Schema 正负例、可选属性省略、非法 required、标准字段入合同、结构化 unknown 占位和无 limitations 报告。示例输出不能复制为正式案例结论。
