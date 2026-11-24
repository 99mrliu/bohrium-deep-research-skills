---
name: slr-dual-screen
description: >
  系统性文献综述技能，签名能力为「双人独立筛选的判定一致性治理」：Agent 分两个
  互相隔离的 pass 扮演筛选者 A/B，对题录级与全文级两轮筛选逐条留痕，用 Cohen's
  kappa 量化一致性，分歧强制仲裁留痕，最终纳入集以 SHA-256 冻结、可验篡——直接
  回应"换一个人拿着同样的输入和记录能否复跑出基本一致的纳入集"。触发场景：需要
  可复核纳入/排除依据、一致性量化与防篡改留痕的系统综述任务。差异化能力：pass
  隔离纪律、条款版本化（治理筛选途中悄悄放宽标准）、kappa 处置路径、冻结/解冻
  留痕。边界：脚本只做解析、校验、计数、哈希等确定性工作；检索、判定、质量评价
  与综述写作由模型完成并如实声明不确定性；示例数据均为合成示例。
---

# slr-dual-screen：双人独立筛选 + kappa 一致性 + 仲裁留痕 + 纳入集冻结

## 1. 适用场景与边界

适用：组织方给定研究问题与候选题录（或需现场检索）的系统性文献综述任务，
尤其重视纳入/排除的可复核性、判定一致性与过程防篡改的场景。

边界：
- 不负责单篇文献的精读翻译、论文写作润色与统计合并（meta 分析数值计算）；
- 脚本（纯 Python3 标准库）只做确定性工作：解析、校验、kappa 计算、冻结哈希；
  判定、条款解释、质量评价、综合写作由模型完成；
- 材料不足以支撑双人筛选时降级为 single-screener 模式，status=partial 并声明
  （见 references/dual_screen_protocol.md 第 4 节），不得伪造第二个筛选者。

## 2. 运行环境

- 平台：评测器把本技能安装到 `/skills/weekly-skill`；案例输入 `/input/case.json`
  + `/input/task.md`；工作目录 `/app/work`；交付 `/app/output/result.json`。
- 脚本定位兜底（安装路径不确定时）：

  ```bash
  find / -maxdepth 5 -name "screen_check.py" -path "*dual-screen*" 2>/dev/null
  # 找到后以该文件所在目录的上一级为 $SKILL（即 $SKILL/scripts/screen_check.py）
  ```

- 退出码约定（全部脚本一致）：**0=通过；2=输入/材料不足（诚实降级）；3=校验
  失败（发现违反规则）**。错误信息带规则码（S1–S5、K1–K3、A1–A4、V1）。
- 每个脚本支持 `--help`。

## 3. 工作流程

> 预算纪律：一切可确定性做的事交给脚本；模型只做判断、解读与写作。
> 第 2 步必须把 result.json 骨架落盘，之后增量填充，防止中断时交付物全失。

### 步骤 0：环境确认
定位 `$SKILL`，确认 `/input/case.json`、`/input/task.md` 与随案材料存在；
`cd /app/work`。

### 步骤 1：读案例（parse_case.py）
```bash
python3 $SKILL/scripts/parse_case.py --case /input/case.json --task /input/task.md --out case_summary.json
```
得到 case_id、output_contract 字段表、材料清单与 warnings。case.json 缺失或
损坏 → exit 2，此时如实生成 failed/partial 骨架并说明，不编造输入。

### 步骤 2：保底脚手架（scaffold_result.py）
```bash
python3 $SKILL/scripts/scaffold_result.py --case-summary case_summary.json --out /app/output/result.json
```
骨架含合同全部字段，status=partial。此后每个环节完成后增量填充对应字段
（缺字段时用 scaffold_result.py 不带 --force 补齐，不会覆盖已填充内容）。

### 步骤 3：研究问题结构化拆解（模型）
用 PICO（或 SPIDER）拆解研究问题，写入 result.json.product 的开头部份，
并列出检索概念块（人群/干预/对照/结局/设计）。

### 步骤 4：检索式设计（模型，必要时现场执行）
为每个概念块写检索式：数据库/字段/布尔逻辑/同义词与受控词/时间与语言限制，
并**逐段说明意图**（"该段用 OR 扩同义词防漏检"）。若案例已给题录清单，则记录
其来源与检索边界到 sources，不虚构检索过程。检索结果落盘为 records.json
（每条含 record_id、title、abstract、year、language）。

### 步骤 5：条款化纳排标准先行（签名环节 1/4）
产出 criteria.json，**版本号从 v1.0 起**，含 IN-* 纳入条款与 EX-* 排除代码表
（设计原则见 references/dual_screen_protocol.md 第 3 节）。
**版本纪律**：筛选途中修改条款必须 ①升版本 ②在 change_records 写
{time, field:"criteria", from, to, reason, affected_records} ③双方重筛受影响
记录。禁止只改标准不回筛——这是治理"纳排标准被悄悄放宽"的核心纪律。

### 步骤 6：round 1 题录级双人独立筛选（签名环节 2/4）
- **pass 1（筛选者 A）**：逐条判定全部记录，写 decisions_round1.jsonl
  （schema：{record_id, round:1, screener:"A", decision, reason_code, reason_text}）。
- **pass 隔离指令（必须执行）**：开始 pass 2 前，不得读取/引用/复述 pass 1 的
  任何判定与理由；pass 2 的 reason_text 只能引用记录原文与条款编号，出现
  "同上""与 A 一致"即隔离失败须重写；pass 2 完成后禁止回头修改任何原始判定。
  尽量在干净上下文中执行 pass 2（只给 records + criteria + schema）。
- **pass 2（筛选者 B）**：独立逐条判定，append 到 decisions_round1.jsonl。
- 校验与一致性：
  ```bash
  python3 $SKILL/scripts/screen_check.py --records records.json --decisions decisions_round1.jsonl --round 1 --criteria criteria.json
  python3 $SKILL/scripts/kappa.py --decisions decisions_round1.jsonl --round 1 --out agreement_report_round1.json
  ```
  exit 3 时按规则码逐条修复（S2 缺失补判定、S3 补理由）；kappa < 0.6 按
  references/kappa_guide.md 第 3 节处置（澄清条款→加轮→扩大仲裁）。
- 本轮分歧先出仲裁草案（adjudication.jsonl 中 round=1 的行），确定存活记录
  清单 records_round2.json（共识纳入 + 仲裁纳入）。

### 步骤 7：round 2 全文级双人独立筛选
对 records_round2.json 逐条获取全文（PDF 现场解析：pdftotext / OCR），同法
双 pass 判定（重点核实全文可得性、设计真实性、结局数据），screen_check +
kappa（round 2），分歧写入 adjudication.jsonl（round=2 的行）。全文不可得
的记录按 EX-FULLTEXT 处理并如实记录获取尝试。

### 步骤 8：仲裁 + 纳入集冻结（签名环节 3/4）
```bash
python3 $SKILL/scripts/adjudicate.py \
  --disagreements agreement_report_round1.json agreement_report_round2.json \
  --rulings adjudication.jsonl \
  --decisions decisions_round1.jsonl decisions_round2.jsonl \
  --out frozen_set.json
python3 $SKILL/scripts/adjudicate.py --verify frozen_set.json \
  --rulings adjudication.jsonl --decisions decisions_round1.jsonl decisions_round2.jsonl
```
规则：每条分歧有且仅有一条仲裁（A1）；rationale ≥ 20 字符且含条款编号+记录
事实+结论（A2）；uncertain 只许经仲裁转判（S4）；冻结后任何改动使 --verify
失败（V1）。仲裁人资格与冻结/解冻流程见 references/adjudication_policy.md。

### 步骤 9：质量评价（模型）
对 frozen_set.json 的每条纳入记录做逐维度质量评价（随机化、分配隐藏、盲法、
失访、选择性报告等，按案例研究类型选量表），每维度给判断+依据位置（页码/
段落），并说明该等级如何影响结论强度。写入 evidence_matrix 的 quality 子字段。

### 步骤 10：综合结论（模型）
基于 evidence_matrix 写 product：每条论断回链到具体记录与证据位置；单列
**冲突证据**与**研究空白**；全文用【事实】（材料直接支持）/【推断】（合理外推）
/【无法确定】（材料不足）三级标注，第三类同时进 uncertainty。

### 步骤 11：组装 result.json + 自查
按下表填充全部字段，然后执行第 6 节自查。

## 4. 输出合同映射表

| result.json 字段 | 来源 |
|------|------|
| case_id | case_summary.json |
| skill_name | 固定 "slr-dual-screen"（scaffold 写入） |
| status | 全链走完且 verify 通过=complete；单人筛选/材料缺失/kappa 未达标但已声明=partial；无法运行=failed+原因 |
| product | 步骤 3、10：PICO、综合结论（含冲突证据、研究空白、三级标注） |
| evidence_matrix | 每条记录一行：{record_id, round1{A,B 判定+理由}, round2{...}, adjudication{final,rationale,arbitrator}, resolution(consensus/adjudication), quality, evidence_loc} |
| sources | 检索式与数据库记录 / 案例给定材料清单；criteria.json 版本历史 |
| uncertainty | kappa 值与样本量、患病率悖论说明、无法获得全文的记录、【无法确定】论断、single-screener 声明 |
| change_records | criteria 版本变更、冻结/解冻记录（含新旧 SHA-256）、人工改判 |
| counts | 各轮 screened/agree/disagree/kappa、total_decisions、total_rulings、included/excluded（与 frozen_set.json.counts 一致） |
| checks | 每次脚本调用：{script, args 摘要, exit_code, 规则码摘要} |

## 5. 异常处理

| 异常 | 处置 |
|------|------|
| 检索为空 | 如实记 counts.retrieved=0，status=partial，product 说明检索式与可能原因（过严条款/数据库覆盖），不编造文献 |
| 数据库或接口超时 | 重试≤2 次并记录；仍失败则用已得材料降级，sources 注明覆盖缺口，uncertainty 声明 |
| 全文不可得 | round 2 判 EX-FULLTEXT，记录获取尝试（渠道、日期），进 uncertainty |
| 术语同义歧义 | 检索式用 OR 扩同义词；判定歧义走 uncertain→仲裁，不得单方猜测 |
| 纳排条款冲突 | 按 criteria.json 声明的优先级裁决；条款本身歧义 → 升版本+change_records+重筛受影响记录 |
| 纳入证据互相矛盾 | product 中单列冲突证据，双方论据各回链原文位置，结论按质量评价加权并降置信 |
| 权限不足（文件/网络） | 不绕过；改用可读路径，status=partial 并说明被阻断的环节 |
| 预算/时间将尽 | 优先保证 frozen_set.json 与 result.json 骨架已落盘；剩余环节在 checks 中标注未完成项 |
| kappa 过低 | 见 kappa_guide.md 第 3 节：澄清条款→加轮→扩大仲裁；--enforce 场景 exit 3 时必须处理后再继续，不得跳过 |
| 材料不足双人筛选 | single-screener 模式：status=partial，counts.single_screener=true，uncertainty 声明可复现性未验证 |
| 分歧过多（>30%） | 判定条款体系失败，回到条款澄清重做，change_records 留痕，不靠仲裁硬压 |
| 冻结后需修改 | 走解冻流程：change_records 写 unfreeze（含旧 SHA-256）→修改→重跑校验→--force 再冻结→写 refreeze（含新 SHA-256） |

## 6. 自查方法

1. 交付前运行 `python3 $SKILL/scripts/selfcheck`（应为 exit 0；它用合成示例
   断言正负例与手算 kappa，与正式案例数据无关）；
2. `python3 $SKILL/scripts/adjudicate.py --verify frozen_set.json --rulings ... --decisions ...` 必须为 exit 0；
3. 逐字段核对 result.json：合同字段无缺失；counts 与 frozen_set.json.counts
   一致；evidence_matrix 每行的判定都能在两份 decisions jsonl 中找到原文行；
4. 检查 change_records：criteria 是否仍是 v1.0？若升过版本，是否有对应重筛
   记录；冻结后是否有人动过 decisions/frozen_set；
5. 检查诚实性：partial/failed 是否写明界限；uncertainty 是否包含 kappa 样本量
   与局限；【无法确定】项是否与 uncertainty 一致。

## 7. 最小调用示例（可直接复制执行）

```bash
SKILL=$(dirname $(find / -maxdepth 5 -name "screen_check.py" -path "*dual-screen*" 2>/dev/null | head -1))/..
cd /app/work
python3 $SKILL/scripts/parse_case.py --case /input/case.json --task /input/task.md --out case_summary.json
python3 $SKILL/scripts/scaffold_result.py --case-summary case_summary.json --out /app/output/result.json
# …步骤 3–5：模型产出 records.json 与 criteria.json(v1.0)…
# …步骤 6 pass1(A)/pass2(B 隔离) 写 decisions_round1.jsonl…
python3 $SKILL/scripts/screen_check.py --records records.json --decisions decisions_round1.jsonl --round 1 --criteria criteria.json
python3 $SKILL/scripts/kappa.py --decisions decisions_round1.jsonl --round 1 --out agreement_report_round1.json
# …round 2 同法…
python3 $SKILL/scripts/adjudicate.py --disagreements agreement_report_round1.json agreement_report_round2.json \
  --rulings adjudication.jsonl --decisions decisions_round1.jsonl decisions_round2.jsonl --out frozen_set.json
python3 $SKILL/scripts/adjudicate.py --verify frozen_set.json --rulings adjudication.jsonl \
  --decisions decisions_round1.jsonl decisions_round2.jsonl
python3 $SKILL/scripts/selfcheck   # 交付前自查，应 exit 0
```

合成示例（非正式案例）见 `$SKILL/examples/`，含手算 kappa 与全部负例。
