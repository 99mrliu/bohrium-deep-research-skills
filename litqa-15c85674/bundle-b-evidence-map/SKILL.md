---
name: litqa-evidence-map
description: 文献智能问答的"证据定位"路线。当任务给出 /input/case.json（带段落编号的论文案例包与中文问题清单）并要求把结构化结果写入 /app/output/result.json 时使用。本 Skill 的重心在证据侧：把复合中文问题机械拆成子问清单、由模型把每个子问翻译为英文关键词后做 BM25-lite 候选段落排序、为每段抽取"数值+单位+上下文"建立全量数值总表、并对任一数量关键词做跨段落冲突扫描（CONFLICT / MULTIVALUE / NONE 三级）。答案中的每个数值都必须先出现在证据地图里再被引用；查无提及的数量按"材料未报告"诚实处理。适用于跨章节整合、数值密集、含比较与条件追问的文献问答。
---

# 证据定位（litqa-evidence-map）

版本：1.0.0　运行环境：Python 3.10+（仅标准库）、shell。零外部依赖。

**方法重心**：低推理档模型的主要失分点不是"不会读"，而是**读错地方、漏掉数值、
把不同对象/条件的数值混写**。本 Skill 在模型动笔之前先建三张地图——
**子问分解表、段落候选排序、数值-单位总表**——并提供一个机械的数量冲突扫描器。
模型只做三件它擅长的事：翻译关键词、读候选段落、成文作答；
定位、抽取、比对全部交给确定性脚本。

## 1. 运行契约

- 输入：`/input/case.json`（案例/论文标识、材料版本、段落清单、任务说明、问题清单）。
  Skill 装入路径以 `/skills/literature-qa`（或 `/skills/weekly-skill`）为根，
  引导时复制脚本到 `/app/work/scripts`（见第 3 节）。
- 工作目录：`/app/work/`；输出目录：`/app/output/`。
- 主输出：`/app/output/result.json`，同时写相同内容到 `/app/answers.json`（旧契约兼容）。
- `result.json` 字段契约：`case_id`、`paper_id`、`material_version` 与输入一致；
  `answers[]` 覆盖全部问题，每项含 `question_id`、`answer`、`conditions[]`、
  `status`（`answered|partial|insufficient_evidence|input_error`）、`claims[]`
  （`claim_id/text/kind`（`reported|inferred`）/`evidence[]`（`paragraph_id`+逐字 `quote`））、
  `unanswered_parts[]`；`coverage`（`read_sections`/`unread_sections` 含原因）。
  `output_contract` 的额外字段逐一照抄。
- **诚实 partial**：任何失败都留下如实状态的 result.json，不编造答案或引文。

## 2. 流水线（每案例约 8–12 次工具调用）

```bash
mkdir -p /app/work /app/output
SRC=$(find /skills -maxdepth 3 -name evidence_map.py -path '*/scripts/*' 2>/dev/null | head -1)
[ -z "$SRC" ] && SRC=$(find /app /opt -maxdepth 5 -name evidence_map.py -path '*/scripts/*' 2>/dev/null | head -1)
cp -r "$(dirname "$SRC")" /app/work/scripts && ls /app/work/scripts

# 步骤 1：建索引 + 数值总表
python3 /app/work/scripts/evidence_map.py index --case /input/case.json --work /app/work
# 产出 index.json 与 numbers.md；输入非法时此步直接报错退出——先写
# status=input_error 骨架（可手写最小骨架或复用任意同结构工具）后如实结束。

# 步骤 2：通读 numbers.md 全表 + 全部候选段落之前，先做子问分解与定向排序。
# 对每个子问，把中文翻译为英文关键词（保留原文术语与数字），然后：
python3 /app/work/scripts/evidence_map.py subqs --index /app/work/index.json --work /app/work \
    --terms "Q1S1:yield strength,modulus;Q1S2:compression,room temperature;Q2S2:fatigue life"

# 步骤 3：按 evidence_map.md 的候选顺序定向阅读（只读候选段，高分段必读，
# 低分段抽查；全文很短时全读）。引用数值前必须与 numbers.md 核对数值+单位。

# 步骤 4：凡答案要写数值或"X 比 Y 高/低"前，对关键词跑冲突扫描：
python3 /app/work/scripts/evidence_map.py conflicts --index /app/work/index.json --key "yield strength"
#  CONFLICT(退出码3)：同语境不同值——并列各值+段落出处，在 claim 中注明冲突；
#  MULTIVALUE(退出码0)：同单位多取值——逐段保留对象与条件，不得混写；
#  NONE(退出码4)：查无此数量——只有通读相关章节确认后，才写"材料未报告"，
#  并标 insufficient_evidence（或在 answer 中如实说明后按需定 status）。

# 步骤 5：成文作答并写 /app/output/result.json + /app/answers.json，
# 规则见 references/evidence-rules.md。作答前自查：answer 里每个数值都
# 能在 numbers.md 里找到吗？找不到就换证据或如实降 status。
```

## 3. 工具子命令与退出码

| 子命令 | 作用 | 退出码 |
|-|-|-|
| `index` | 解析、索引、抽取数值-单位提及，写 index.json / numbers.md | 0 正常；1 输入非法 |
| `subqs` | 复合问题拆子问 + 候选段落排序 + 数值提及提示，写 evidence_map.md | 0 |
| `query` | 单个子问的即时检索（调试与追问用） | 0 |
| `conflicts` | 关键词跨段落数值扫描 | 0 唯一/MULTIVALUE；3 CONFLICT；4 无提及 |

## 4. 异常处理与已知限制

- 中文问题直接检索无命中是**预期行为**：材料是英文、问题为中文，
  必须先把子问翻译为英文关键词（`--terms`），这是流程的一部分而非失败。
- BM25-lite 是纯词项匹配，不处理同义词扩展；翻译关键词时把可能的
  同义表述都列上（如 "hot isostatic pressing, HIP, post-processing"）。
- 冲突扫描基于数值邻近窗口（±90 字符），会误收窗口内邻近数值；
  CONFLICT 判定要求相同归一化语境，误报率低，但最终的并列/取舍判断仍由人读原文完成。
- 不解析 PDF、不联网检索；输入只有 case.json。

## 5. 资源清单

| 路径 | 作用 |
|-|-|
| `scripts/evidence_map.py` | index / subqs / query / conflicts 四子命令 |
| `references/evidence-rules.md` | 子问分解原则、关键词翻译规范、数值引用纪律、冲突处置细则 |
| `examples/synthetic-case.json` | 合成示例输入（虚构论文，非正式案例） |
| `examples/run-record.md` | 合成示例的本地端到端真实运行记录 |
| `GITHUB_URL.txt` | 本作品的 GitHub 公开链接 |
