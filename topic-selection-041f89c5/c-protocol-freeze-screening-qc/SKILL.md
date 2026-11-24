---
name: protocol-freeze-screening-qc
description: 过程质量控制取向的科研选题文献筛选技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与一批文献材料，要求围绕固定研究问题完成系统筛选、证据整理、综述或选题评估，并在 /app/output 交付结构化 result.json 时使用。核心立场：综述可信度来自过程可审计——纳排标准先编号化并声明冻结时间（protocol_lint.py 检查协议结构），筛选决策逐条留痕于 CSV 日志，screening_audit.py 对照冻结协议机审每条决策（排除必须引用标准编号与理由、协议前决策判违例、待定必须写缺口），并输出 PRISMA 式流量计数。不适用：单篇文献精读、无筛选环节的短评。
---

# protocol-freeze-screening-qc：先冻结规则，再筛选文献

## 核心主张

"先看文献再补规则"是选题综述最普遍的失真：规则被顺眼的文献反向塑造，排除决策无据可查，综述成了事后叙事。本技能强制倒置顺序：**协议编号化并冻结 → 逐条决策留痕 → 机审对账**。结论质量可能有边界，过程必须全程可复核；评审者不看自述，看日志与 QC 报告。

## 运行时契约

1. 输入在 `/input`：`task.md`、`case.json`（`case_id`、`output_contract`）、文献材料（PDF/TXT/JSON/CSV）。逐文件读真实内容；PDF 用实际可用工具从原始文件解析，不假设预提取文本层。
2. 若存在 `/input/environment/resources.yaml`，先读确认可用工具。
3. 中间产物入 `/app/work`，最终交付入 `/app/output`；`result.json` 含 `case_id`（逐字一致）与 `output_contract` 全部原始字段。
4. 预算：约 64 次模型请求、900 秒、16384 token/响应。第一阶段即写 result.json 骨架（契约字段=null、status=in_progress），每阶段回填。
5. 诚实状态：`status` ∈ {success, partial, failed}；partial 写明缺口；检索为空、文献过少、证据冲突分别如实说明。
6. 禁止伪造：检索不到不写"尚无人研究"，日志不后补，决策不改日期。

## 工作流程

### 阶段 0：契约骨架与材料登记

登记 `/input` 全部文件（名称、字节数、格式）到 `/app/work/inventory.md`；摘出 case_id 与 output_contract 字段；写 `/app/output/result.json` 骨架。

### 阶段 1：协议制定与冻结（打开任何文献全文之前）

按 `references/protocol_format.md` 写 `/app/work/protocol.md`：

- 研究问题一句话可检验陈述；
- 纳入标准 `[I1] [I2] ...`、排除标准 `[E1] [E2] ...`：每条是对单条文献记录可机械执行的判定句（含阈值、时间窗、研究类型），不许"相关者入"式空标准；
- `冻结时间: <ISO-8601>` 行；
- 证据来源声明：输入文献集为第一来源；有联网通道且任务允许则登记完整检索式，否则写明"覆盖边界=输入文献集"。

运行 `python3 /skills/weekly-skill/scripts/protocol_lint.py --protocol /app/work/protocol.md --out /app/work/protocol_lint`，违例修复后再进入筛选。

### 阶段 2：筛选留痕

对每条候选文献在 `/app/work/screening_log.csv` 写一行（格式见 `references/screening_log_format.md`）：decision ∈ {include, exclude, hold}；exclude 必须引用 `[E*]` 编号并写理由；hold 必须写缺什么信息；decided_at 填当天日期。协议冻结后确需修订协议时，在 `## 修订记录` 区加一条（日期+原因），**修订本身留痕，旧条目不删**。

### 阶段 3：机审对账（本技能核心）

```
python3 /skills/weekly-skill/scripts/screening_audit.py \
    --protocol /app/work/protocol.md \
    --log /app/work/screening_log.csv \
    --out /app/work/screening_qc
```

读 `screening_qc.md`：违例（R1–R6，规则见 `references/screening_log_format.md`）逐条修复或登记为已知缺陷；PRISMA 式计数原样进入综述的方法段。纳入 0–1 篇时不许放宽标准硬凑，转异常处理。

### 阶段 4：证据矩阵与综合

纳入文献逐篇抽取证据（任务/方法/数据/评价/结论/来源定位）入 `/app/work/evidence_matrix.md`；综合四项交付：已有工作比较（标出真正相近与不可比工作及原因）、创新点逐条判定（附矩阵行号与检索边界）、可行性前提（标 `[来源]`/`[假设]`）、研究空白与冲突证据取舍。每条结论可回到矩阵行。

### 阶段 5：收口

回填 result.json；`protocol.md`、`screening_log.csv`、`screening_qc.md`、证据矩阵复制或引用到 `/app/output`。终检：PRISMA 计数与日志逐行一致；每条排除都能报出标准编号。

## 异常处理

| 情形 | 处置 |
|-|-|
| 候选为 0 或全部排除 | status=partial；交付协议、空日志、QC 报告与"无法形成综合"说明；给出补文献后的复跑步骤 |
| 仅 1–2 篇纳入 | 正常出矩阵，综合降级为"初步证据"并注单源风险 |
| 协议 lint/机审违例修不好 | 在 result.json 不确定性字段登记违例条目与原因，不静默 |
| 文献不可解析 | 登记 unreadable 并排除，不用摘要冒充全文 |
| 预算将尽 | 立即回填当前状态（partial），优先保协议+日志+QC 三件套完整 |

## 红线

- 不许先筛选后写协议；不许后补/篡改日志日期；不许无理由排除；不许为凑数放宽标准；不许只交付支持性证据。

## 最小示例

`examples/` 内有**合成示例**：虚构协议与 8 行筛选日志（故意埋 3 类违例），演示 lint 通过→机审计出违例→修复后全绿的全过程，见 `examples/minimal_example.md`。
