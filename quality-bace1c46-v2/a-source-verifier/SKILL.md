---
name: upstream-source-verifier
description: >-
  上游来源真实性核验技能。在做出任何文献质量判断之前，先核验所提供的材料本身：
  为每个输入文件建立指纹（sha256/大小/类型），解析离线 Crossref / EuropePMC
  API 响应快照，将快照元数据与文档正文文本层交叉核对，检测重复、改名文件、
  版本冲突与元数据不一致，并将每个来源标记为 verified / mismatch /
  unverifiable。当任务提供文献材料（PDF/TXT）及其元数据快照、且要求做文献质量
  评估、综述或任何需要引用来源可信度的判断时触发；凡下游论断需要绑定来源时，
  只允许绑定 verified 来源。
---

# upstream-source-verifier（上游来源真实性核验）

## 1. 解决什么问题

文献质量评估的第一公里不是"读文献"，而是"确认拿到的材料就是它声称的东西"。
常见坑：下载后改名的 PDF、预印本与正式发表版本混放、同一条目被增量导入两次、
快照里的年份/DOI 与正文对不上。本技能在任何质量判断**之前**建立一份
**provenance ledger（来源真实性台账）**：

- 每个输入文件的指纹（相对路径、字节数、sha256、类型猜测）；
- 每个离线元数据快照的解析结果（Crossref / EuropePMC 两种风味）；
- 快照元数据 × 文档正文的逐字段交叉核对结论；
- 重复记录、版本冲突（同 DOI 不同年份/类型）的显式清单；
- 每个来源的判定：`verified` / `mismatch` / `unverifiable`。

铁律：**mismatch 只上报，绝不静默修复，绝不编造**；下游论断只允许绑定
`verified` 来源；无法核验的写明原因并进入 uncertainties。

## 2. 适用条件

- 评测器将本技能安装在 `/skills/weekly-skill`；
- 代理输入为 `/input/case.json` 与 `/input/task.md`；
- 材料可包含真实 PDF/TXT 与离线 Crossref/EuropePMC JSON 快照；
- **完全没有网络**：绝不发起任何 fetch/下载，所有信息只来自本地文件；
- 任何需要先确认"来源可信"再谈"内容质量"的任务。

不适用：材料为零时（此时照走流水线，产出诚实的 partial 结果并解释）。

## 3. 输入契约（防御式解析）

`case.json` 的结构不可假设，必须防御式解析：

- **文档清单**：可能嵌套在任意键下——`documents` / `papers` / `references` /
  `files` / `literature` / `corpus` / `materials` 等。递归搜索整个 JSON；
  找不到就退化为"遍历 /input 目录本身"（fingerprint.py 默认即如此），
  **永不崩溃**。
- **case_id**：按 `case_id` → `id` → `caseId` 顺序回退，都没有则
  `"unknown_case"`。
- **output_contract**：递归搜索键名 `output_contract` / `contract` /
  `output_fields` / `required_fields`；找到后镜像其声明的每一个字段到
  result.json。本技能只负责来源核验，这些字段若无法在核验阶段填写，填
  `null` 并在 uncertainties 中说明，**绝不填编造值**。
- `case.json` 与 `task.md` 是编排文件而非来源：fingerprint 会登记它们，
  但 build_result 将其排除在 provenance ledger 与 status 判定之外
  （并记入 change_records）。

## 4. 运行方式（命令行）

所有脚本仅依赖 Python 3 标准库；PDF 文本层提取可选依赖系统 `pdftotext`
（没有就把 PDF 判为 unverifiable，不报错）。

```bash
B=/skills/weekly-skill
# 第 1 步：指纹登记 + 立刻写出诚实的不完整 result.json 骨架
python3 "$B/scripts/fingerprint.py" \
    --input-dir /input --workdir /app/work \
    --output-dir /app/output --case /input/case.json

# 第 2 步：快照元数据 × 正文交叉核对
python3 "$B/scripts/crosscheck.py" --workdir /app/work

# 第 3 步：汇总最终 result.json 与 provenance_report.md
python3 "$B/scripts/build_result.py" \
    --workdir /app/work --output-dir /app/output --case /input/case.json
```

退出码约定：`0` 正常（含部分文件无法核验）；`1` 校验失败（如输入目录不存在、
manifest 缺失）；`2` 参数用法错误。

## 5. 工作流（模型侧操作说明）

**脚本先行，模型只做脚本做不了的语义裁决。**

1. **先跑 fingerprint.py（含骨架 result.json）**。这是预算保险：即使后续
   步骤全部失败，`/app/output/result.json` 也已存在一份诚实的不完整结果
   （`status=in_progress`，uncertainties 注明 verification pending）。
2. **跑 crosscheck.py**，读 `verification_summary.md` 与人类可读的逐对明细。
3. **模型语义裁决**（仅限脚本做不了的事）：
   - 判断某组 mismatch 是"预印本 vs 正式版"还是"拿错了文件"这类语义归因，
     写入 uncertainties 或 change_records（措辞必须是推测性的，不得断言）；
   - 对非拉丁文字标题、仅摘要条目、无文本层扫描件执行**弃权**
     （abstain → unverifiable + 原因），不要强行比对；
   - 把 output_contract 中与来源核验无关的下游质量字段保持为 `null` +
     说明，或在自己确有把握且已绑定 verified 来源时再填。
4. **跑 build_result.py** 产出最终交付物。如需把模型的语义裁决并入
   uncertainties，可在第 3 步后直接编辑 result.json 的 `uncertainties` /
   `change_records` 数组（保持 JSON 合法）。
5. 增量改进：时间充裕时可补充更多来源的裁决，但任何时刻 result.json 都
   必须是合法且诚实的。

## 6. 预算分配

总预算：**≤64 次模型请求、900 秒**。建议分配：

| 阶段 | 模型请求 | 说明 |
|---|---|---|
| 脚本三步（指纹/核对/汇总） | 0–2 | 全是脚本，模型只发命令 |
| 阅读摘要 + 语义裁决 | 3–8 | 只看 verification_summary.md，不逐文件通读 |
| 异常处理与补漏 | 2–6 | 只在有 mismatch/unverifiable 时花费 |
| 终检 result.json 合法性 | 1 | json.load 校验 |

原则：第一个脚本步骤内就落盘骨架 result.json；此后每步只增不改其诚实性。
剩余预算不足时，优先保证 result.json 合法、status 诚实、不确定项写全。

## 7. 异常处理

| 异常 | 行为 |
|---|---|
| /input 为空或没有来源文件 | 照跑，result.json 为 `partial` + 空 ledger + 解释 |
| case.json 缺 output_contract | 继续，uncertainties 注明"未找到输出契约" |
| JSON 快照解析失败 | 该文件 `unverifiable`（原因写入 note），流程不中断 |
| PDF 无 pdftotext / 扫描件无文本层 | 该文件 `unverifiable`（原因明确），其余继续 |
| 快照记录缺标题/年份/DOI/作者 | 缺哪个字段就少核哪个字段；全缺 → `unverifiable` |
| 检测到重复/版本冲突 | 如实列入 duplicates / version_conflicts 与 uncertainties，**不合并、不修复** |
| 任何脚本异常 | 就地降级，绝不 crash；骨架 result.json 保底 |

## 8. result.json 契约

最终交付 `/app/output/result.json`，顶层字段：

- `case_id`：防御式回退链取值；
- `status`：`success`（全部来源 verified）/ `partial`（存在 mismatch 或
  unverifiable，或零来源；必须陈述限制）/ `failed`（无法产出任何核验）；
- `output_contract`：镜像 case 声明的每个字段；本技能填不了的为 `null` +
  uncertainties 说明；
- `main_results`：含 `provenance_ledger`（每来源：指纹、快照风格、判定、
  `usable_for_assessment` 布尔）、`counts`、`duplicates`、
  `version_conflicts`；
- `evidence`：manifest.json / verification.json / verification_summary.md
  的路径（来源定位器）；
- `uncertainties`：所有限制、弃权原因、不一致清单；
- `change_records`：流水线动作列表（可为空数组）。

同时产出 `/app/output/provenance_report.md`（人类可读表格）。

## 9. 参考资料

- `references/snapshot_fields.md`：Crossref / EuropePMC 快照字段结构与常见
  不一致模式；
- `references/veracity_rules.md`：归一化规则、模糊匹配阈值、判定阶梯、
  弃权条件、判定到 status 的映射；
- `examples/`：完全合成的可运行示例（含真实运行输出节选）。
