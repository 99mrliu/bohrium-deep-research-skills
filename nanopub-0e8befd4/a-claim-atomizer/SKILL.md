---
name: claim-atomizer
description: 面向科研阅读的断言拆解技能。把论文段落拆成逐条可独立判真的原子断言，保留条件、范围与模态限定，映射受控关系词表，并用确定性脚本核验粒度与限定丢失。适用于 Nanopublication 生成、结论结构化、断言粒度自检。不适用：整篇翻译、图表像素级读数、无原文支撑的核验。
---

# claim-atomizer — 原子断言拆解与粒度核验

**核心立场：一条断言只承载一个可独立判真的事实；任何限定词丢失都是错误，不是风格问题。**

本技能的重心在**断言拆解**这一上游环节：先定粒度，再谈证据与导出。证据定位、来源元数据、
结构化导出按通用契约完成，但不另起重型管线。全部脚本仅用 Python 3.9+ 标准库。

## 运行契约（平台评测环境）

1. 先读 `/input/case.json`、`/input/task.md` 与 `environment/resources.yaml`（如存在）。
   记录 `case_id`、任务边界、`output_contract` 要求的字段与文件路径。**任务自带 schema
   优先于本技能任何示例字段**；按实际 schema 适配命名与嵌套。
2. 材料按 manifest 路径读取真实文件。PDF 用环境中已有的 `pdftotext -layout` 或 PyMuPDF
   提取，保留物理页序；扫描件无文本层时按「异常处理」降级，不编造文本。
3. 工作文件放 `/app/work`；交付物放 `/app/output`，其中 `result.json` 必须含原
   `case_id` 与 `output_contract` 全部字段。断言、证据定位、来源、置信度依据、运行状态、
   不确定项按任务字段逐一落齐。
4. 预算：64 次模型请求、900 秒。**第一遍读完材料即可写的部分先写 `result.json`
   草稿（含诚实 partial 状态），再迭代补全**；不在格式打磨上耗尽预算。
5. 本技能目录记为 `SKILL_DIR`（通常 `/skills/weekly-skill`），脚本用
   `python3 SKILL_DIR/scripts/atomize_lint.py ...` 调用，路径一律用绝对路径。

## 拆解工作流（Agent 逐步执行）

### 第 1 步：圈定拆解范围

按 task.md 圈定需要覆盖的章节/段落/问题。全文级任务须覆盖结果、讨论、方法要点与局限；
局部任务读完指定区域及其定义所依赖的上下文。把覆盖清单写入 `/app/work/coverage.md`，
每区域标 `pending/done`；`coverage.md` 是草稿工具，不替代 result.json。

### 第 2 步：逐段拆解为原子断言

对每段执行（规则细节见 [references/decomposition-rules.md](references/decomposition-rules.md)）：

- **判定粒度**：一个断言恰好一个关系实例，能独立判真。并列谓语、因果复合句、多实验组
  必须拆开；比较基准、联合条件、集合性结论不得被拆强。
- **写自足句**：解析代词与省略主语，断言离开原段仍可读。禁止 `It/This/We` 开头充当下
  断言主语；被动语态要还原真实主客体方向。
- **保留限定**：条件、样本、数据集与版本、数值范围、时间范围写入 `qualifiers`；
  `may/suggest/propose` 等模态写入 `modality`，不得升级为已证实事实。
- **映射关系**：`relation` 只能取自 [references/relation-vocabulary.md](references/relation-vocabulary.md)
  的受控词表；暗示相关不等于因果，无显著差异不等于等价。
- **绑定证据**：给最小充分逐字引文（原语言），记录物理页与章节/段落/表行列定位；
  行号仅在可机械复算时填写，否则只给页+段落定位，不编造坐标。
- **写来源与置信度**：来源记录标题、真实作者、年份、标识符/版本；`confidence` 写证据强
  度理由，不写虚构概率。

字段语义见 [references/field-dictionary.md](references/field-dictionary.md)。参考形态（非正式
答案、非目标条数）见 `examples/twenty_claims/`，是 20 条合成断言样例。

### 第 3 步：机器核验粒度与限定

草稿写入 `/app/work/claims.jsonl`（每行一条断言）后运行：

```
python3 SKILL_DIR/scripts/atomize_lint.py \
  --claims /app/work/claims.jsonl \
  --out /app/work/lint-report.json
```

脚本输出每条断言的 `E_*`（硬错误，退出码 1）与 `W_*`（待审提示，退出码 0）：
复合关系打包、代词主语、数值不在引文、模态升级、范围限定缺失、重复/近重复、关系越出
词表、证据缺失。**硬错误必须修复或删除该断言；待审项逐条人工（Agent）判读，保留的
在 result.json 的审查记录里写明理由**。脚本不证明语义蕴含，最终忠实性仍须对照原文。

### 第 4 步：交付与状态

- `result.json` 写入全部契约字段；已完成区域与未覆盖区域分别说明。
- 状态判据：请求范围全部覆盖且无未决硬错误 → `success`；部分区域未读、无文本层、
  有冲突未裁定 → `partial` 并指明缺口与人工接管位置；材料不可得 → `blocked` 及原因。
- 「未报告」「无法判断」「材料冲突」分别写道，不得把无法判断写成事实。

## 异常处理

| 情形 | 处置 |
|-|-|
| 扫描件/无文本层 | 尝试环境内 OCR；失败则标明受阻页码，交付其余部分，状态 `partial` |
| 断言找不到支撑片段 | 不交付该断言为事实；记入不确定项并给检索范围 |
| 原文内部或跨来源冲突 | 双方断言都保留并各自带来源，标 `conflict`，不擅自裁定 |
| 表格/图证据 | 表格转录单元格+行列表头+脚注；图只能给图号与文字性结论，读不出数值就说不确定 |
| 字段缺失 | 标 `not_reported`，不猜默认值 |

## 本地最小示例（合成）

`examples/minimal/` 含合成段落与 8 条断言草稿；`examples/twenty_claims/` 含同一合成材料的
20 条完整样例。运行方式与预期输出见各目录 README 与 `expected/`。**均为合成示例，非正式
案例结果。**

## 边界与限制

- 原子性、限定保留用启发式机检 + Agent 判读，不声称机器证明语义正确。
- 受控词表是通用科研关系集；任务自带词表时以任务为准并建立映射记录。
- 本技能不做来源指纹与去重跨版本合并（属来源追溯问题），也不做多序列化导出；需要时
  由任务 schema 直接约束输出格式。
