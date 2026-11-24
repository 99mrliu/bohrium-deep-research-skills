---
name: slr-replay-pipeline
description: >
  系统性文献综述的过程工程 Skill。当任务需要走完"研究问题拆解→检索式→条款化纳排→
  两轮筛选→质量评价→证据综合→交付"完整综述链，且要求换人可复跑、中断可续跑、
  计数可轧平时触发。差异化能力：全流程状态机（标准环节 ingest→dedupe→screen_ta→
  screen_ft→appraise→extract→synthesize→deliver）、追加式 SHA-256 登记账（runlog，
  篡改定位到具体步骤的具体文件）、PRISMA 计数五式对账（F1–F5，失衡指名环节与差值）、
  确定性重放器（按 manifest 重跑并逐字节比对，漂移与非确定性步骤定位到步骤）。
  边界：不替代模型做纳排判定与综述写作（模型环节以冻结登记纳入账本）；不精读翻译
  单篇文献；examples 均为合成示例。
---

# slr-replay-pipeline：可复跑、可续跑、可轧账的系统性文献综述

## 1. 适用场景与边界

**适用**：组织方固定案例上的完整系统综述任务；尤其针对两类失败模式——
(1) 任务中断（预算耗尽、会话崩溃、换人接手）后无法定位是哪一步出的错；
(2) 换一个人拿着同样的输入和记录无法复跑出一致的纳入集与结论。

**边界**：
- 本 skill 的机器可检核心是**过程治理**（登记、轧账、重放），检索式构造、纳排判定、
  质量评价、证据综合由模型按 references/ 协议执行，其产物以"冻结登记"入账；
- 不负责单篇文献精读与翻译，不替代学术审查做事实核验；
- 含 LLM 判断的步骤不进 replay manifest（见 6.4 节降级规则）。

## 2. 运行环境

- Python 3 标准库，无第三方依赖；平台评测时 skill 安装于 `/skills/weekly-skill`，
  工作目录 `/app/work`，交付 `/app/output/result.json`。
- **脚本定位兜底**：若相对路径失效，执行
  `find / -maxdepth 6 -name "replay.py" -path "*weekly-skill*" 2>/dev/null | head -1`，
  取其上一级目录的上一级为 `$SKILL`（即 `.../scripts/replay.py` → `$SKILL`）。
  此后所有脚本以 `$SKILL/scripts/<名>` 引用。
- **退出码约定**：0=通过；2=输入/材料不足（诚实降级，报错带 R 码）；3=校验失败
  （V 码=登记/重放校验，F1–F5=轧账规则）。所有脚本支持 `--help`。

## 3. 工作流程（编号步骤）

> 纪律：第 2 步落盘 result.json 骨架保底；**每个环节产物一生成就 runlog 登记**；
> 每个筛选阶段结束就跑 reconcile；交付前 replay 自证。

1. **读案例**：读取 `/input/case.json` 与 `/input/task.md`，确认材料清单。
2. **解析 + 保底骨架**：
   ```bash
   python3 $SKILL/scripts/parse_case.py --case /input/case.json --task /input/task.md \
     --out /app/work/case_summary.json
   python3 $SKILL/scripts/scaffold_result.py --out /app/output/result.json \
     --case-summary /app/work/case_summary.json
   ```
   骨架 status=partial，此后任何中断都有诚实 partial 可交付。
3. **ingest（摄入）**：把原始材料（题录、PDF 等）复制进 `/app/work/materials/`；
   模型撰写研究问题结构化拆解（PICO）与检索式（数据库、字段、布尔逻辑、同义词/
   受控词、时间与语言限制、**每段检索式的意图**），存 `/app/work/search_strategy.md`。
   登记：`runlog.py record --step ingest --actor agent --inputs ... --outputs ...`。
4. **dedupe（去重）**：确定性脚本去重（规范化标题+年份或 DOI），输出
   `duplicates_removed`；把本步命令写入 `/app/work/manifest.json` 的 steps。
5. **条款化纳排标准**：模型把纳排标准写成可判定条款（研究类型/人群/时间/语言/
   全文可得性、条款优先级与冲突处理），存 `/app/work/eligibility.md` 并登记
   （actor=agent；后续任何修改按人工干预纪律处理）。
6. **screen_ta（题录级筛选）**：模型按条款逐条判定，写 `decisions.jsonl`
   （每行 `{"record_id","stage":"ta","decision","reason"}`，一篇一个主理由）；
   脚本汇总计数。登记后**立即轧账**：
   `reconcile.py --flow flow.json --decisions decisions.jsonl`，不平衡按 6.3 节排查。
7. **screen_ft（全文级筛选）**：同上（stage="ft"）；全文不可得必须计入排除理由。
   结束生成/更新 `flow.json` 与冻结纳入清单 `included.json`，登记并轧账（F1–F5 全绿）。
8. **appraise（质量评价）**：模型按适用量表（RCT：RoB2 维度；观察性：NOS 维度）逐研究
   逐维度给出判断+依据位置+总体等级，并说明等级对结论权重的影响；产物登记（冻结，
   不进 manifest）。
9. **extract（证据提取）**：模型按模板提取比较字段（人群/干预/对照/结局/效应值/
   原文定位），形成 evidence_matrix 数据源；登记（冻结）。
10. **synthesize（综合）**：模型形成带证据回链的综合结论，显式区分**材料事实 /
    合理推断 / 无法确定**，列出冲突证据与研究空白；登记（冻结）。
11. **deliver（交付）**：跑齐三次校验并把 exit 码与摘要写入 `result.json.checks`：
    ```bash
    python3 $SKILL/scripts/runlog.py --log /app/work/runlog.jsonl verify
    python3 $SKILL/scripts/reconcile.py --flow /app/work/flow.json \
      --decisions /app/work/decisions.jsonl
    python3 $SKILL/scripts/replay.py --manifest /app/work/manifest.json \
      --workdir /app/work/replay --runlog /app/work/runlog.jsonl
    ```
    `counts` 直接取 flow.json 七字段；组装最终 result.json（见第 4 节映射），
    status 置 complete（若三校验全 0）或 partial（注明界限）。
12. **自查**：按第 6 节清单逐项核对后交付。

**断点续跑操作序列**（任何中断后、换人接手时）：
`runlog.py status`（看首个未登记标准环节）→ `runlog.py verify`（确认已登记产物
未被篡改）→ 从 status 指示环节继续，其输入必须是 verify 通过的已登记产物。
细节与 runlog 丢失处置见 `references/resume_guide.md`。

## 4. 输出合同映射表（result.json 字段从哪来）

| 字段 | 来源 |
|---|---|
| case_id | case_summary.json（parse_case.py 提取） |
| skill_name | 固定 `slr-replay-pipeline`（scaffold_result.py） |
| status / status_reason | 三校验全 0 → complete；任何降级 → partial + 明确界限；无法产出 → failed + 原因 |
| product.review_summary / conclusions | synthesize 环节产物（每条结论带证据回链） |
| product.conflict_evidence / research_gaps | synthesize 环节的冲突证据与研究空白清单 |
| evidence_matrix | extract 环节证据表（文献来源、纳排理由、比较字段、原文定位） |
| sources | 纳入研究的题录元数据（取自真实材料，禁止编造） |
| uncertainty | 无法确定项、证据矛盾、偏倚风险、不可重放步骤说明 |
| change_records | 全部人工干预（每次干预必对应一条 `runlog record --actor human`）+ 关键版本变更 |
| counts | **直接取 flow.json**（identified/duplicates_removed/screened/excluded_title_abstract/fulltext_assessed/excluded_fulltext/included） |
| checks.runlog_verify / reconcile / replay | 三次校验的 `{exit_code, summary}`（deliver 步骤实际运行结果，禁止手填） |

## 5. 签名环节细则

- **runlog 登记**：每环节产物生成即 `record`；同一文件被重写（如 decisions.jsonl
  追加全文阶段）必须重新登记，verify 以最后一次登记为准。
- **reconcile 轧账**：screen_ta 与 screen_ft 两个阶段结束各跑一次；交付前含
  `--decisions` 终轧一次。失衡输出格式示例：
  `F2: screened=120 但 excluded_ta(85)+fulltext(30)=115, diff=5`。
- **replay 自证**：manifest 只收确定性脚本步骤；replay 每步跑两次（识别非确定性），
  再与 runlog 登记哈希逐字节比对；通过输出 `replay: N identical, 0 differ`。

## 6. 异常处理

| 异常 | 处置 |
|---|---|
| 检索为空 | 不编造题录；记录检索式与命中 0 的事实，status=partial，uncertainty 注明检索范围与可能原因（词表过窄/库覆盖不足），给出放宽建议但标注为推断 |
| 数据库或接口超时 | 接口结果不入确定性步骤；重试一次仍失败则记录已得部分，uncertainty 注明覆盖缺口；replay 超 120s 的步骤按 6.4 整改为离线步骤 |
| 全文不可得 | 计入 `excluded_fulltext` 的"全文不可得"理由（严禁静默丢弃）；uncertainty 说明其对结论覆盖的影响 |
| 术语同义歧义 | 检索式中并列同义词/受控词并注明取舍；筛选遇到歧义按纳排条款优先级判定，判定依据写入 decisions.jsonl 的 reason |
| 纳排条款冲突 | 按 eligibility.md 预设优先级裁决；裁决不了的提交人工，干预后 `runlog record --actor human` + change_records |
| 纳入证据互相矛盾 | 不强行合一；进 product.conflict_evidence，按质量等级与样本量分析矛盾来源，结论按高质量证据降权表述 |
| 权限不足（文件/目录不可写） | 切换工作目录到可写路径并在 change_records 记录；result.json 无法写出时把完整内容打印到 stdout 保底 |
| 超时（平台预算耗尽） | 骨架已保底（第 2 步）；runlog 保证已完成步骤不丢；恢复时按断点续跑序列续跑，无需从头再来 |
| 中断恢复 | `status → verify → 从首个未登记标准环节继续`（references/resume_guide.md 第 1 节） |
| 产物被外部修改 | `runlog verify` exit 3 并**指名步骤与文件**；从该步骤已登记输入重新生成产物并重新登记（note 说明），有意修改则补 actor=human 记录 |
| 计数轧不平（reconcile exit 3） | 按序排查：**先 F4**（理由漏记/一篇多理由双计）→ **再 F2**（题录级双计或中途放宽标准补录，对照 decisions.jsonl 逐条核）→ **再查 duplicates**（F1，duplicates_removed 是否取自去重脚本输出）。修正后重跑至 exit 0 |
| 步骤非确定性（replay V4） | 按 references/resume_guide.md 第 2 节清单整改（时间戳/随机数/绝对路径/字典序/环境依赖/自读写不幂等/浮点格式）；整改后重放；**确实无法确定性化**：从 manifest 移除该步骤，产物按冻结输入登记，result.json 降 `status=partial` 并在 uncertainty 声明"步骤 X 不可重放及原因" |
| replay 命令失败/超时（V3/V6） | 多为依赖外部服务或路径错误；改为离线确定性步骤或按上条降级；禁止删除产物或伪造哈希 |

## 7. 自查方法

交付前逐项核对（对应 scripts/selfcheck 的断言逻辑）：

1. `python3 $SKILL/scripts/selfcheck` → exit 0（正例全绿、负例指名故障点）；
2. `runlog.py verify` exit 0——无篡改、无缺失；
3. `reconcile.py --flow flow.json --decisions decisions.jsonl` exit 0——F1–F5 全轧平；
4. `replay.py` 输出 `N identical, 0 differ` 且 exit 0；
5. result.json 的 checks 三项 exit_code 均为 0，counts 与 flow.json 一致，
   change_records 与 runlog 中 actor=human 记录一一对应；
6. 结论逐条有证据回链；事实/推断/无法确定三分已标注；无编造元数据。

## 8. 最小调用示例

以下为合成示例（examples/，synthetic, illustrative），可直接复制执行：

```bash
SKILL=/skills/weekly-skill   # 本地开发时指向 bundle 根目录
cd /app/work 2>/dev/null || cd "$(mktemp -d)"

# 解析 + 骨架
python3 $SKILL/scripts/parse_case.py --case $SKILL/examples/input/case.json \
  --task $SKILL/examples/input/task.md --out case_summary.json
python3 $SKILL/scripts/scaffold_result.py --out result.json --case-summary case_summary.json

# 迷你流水线 + 登记 + 轧账 + 重放（等价于 examples/run_example.sh 核心步骤）
python3 $SKILL/examples/pipeline/step1_dedupe.py \
  --input $SKILL/examples/input/records.json --output deduped.json
python3 $SKILL/scripts/runlog.py --log runlog.jsonl record --step dedupe --actor agent \
  --inputs $SKILL/examples/input/records.json --outputs deduped.json
python3 $SKILL/examples/pipeline/step2_screen_count.py \
  --input deduped.json --output screening.json --decisions decisions.jsonl
python3 $SKILL/examples/pipeline/step3_freeze.py \
  --records $SKILL/examples/input/records.json --deduped deduped.json \
  --decisions decisions.jsonl --output-decisions decisions.jsonl \
  --output-included included.json --output-flow flow.json
python3 $SKILL/scripts/runlog.py --log runlog.jsonl record --step screen_ft --actor agent \
  --inputs decisions.jsonl --outputs decisions.jsonl included.json flow.json
python3 $SKILL/scripts/reconcile.py --flow flow.json --decisions decisions.jsonl
# 预期：reconcile: 全部轧平（含 decisions 对账）：identified=8 → screened=6 → fulltext=4 → included=3

# 负例演示（预期 exit 3，指名 F2）
python3 $SKILL/scripts/reconcile.py --flow $SKILL/examples/negative/flow_broken.json

# 端到端自检（预期 exit 0）
python3 $SKILL/scripts/selfcheck
```
