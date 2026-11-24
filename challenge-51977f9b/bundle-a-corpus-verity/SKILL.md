---
name: slr-corpus-verity
description: >
  系统性文献综述（systematic literature review）上游数据真实性守护 skill。
  触发场景：拿到案例随附的题录清单（records/bibliography/citation 等 JSON/JSONL/
  CSV 导出）后、开始任何筛选之前；或评测快照中题录可能由上游模型生成、存在伪造
  与重复风险时。差异化能力：先建立"可信语料层"——以确定性脚本（V1–V8 规则）
  逐条核验元数据真实性，识别 schema 残缺、非法 DOI、越界年份、精确/近似重复与
  撤稿信号，全部隔离并给出机器可复核的理由，直接产出 PRISMA 的 identified /
  duplicates_removed / quarantined / clean_for_screening 计数；随后仍引导 Agent
  走完整综述链（检索式→纳排→两轮筛选→质量评价→带回链综合）。边界：只做
  本地一致性核验与（可选的）Crossref 在线对照，不把"快照中查不到"当伪造证据；
  DOI 合法但疑似伪造的记录只能标 suspicious 交人工裁决，不断言伪造；不编造任何
  文献元数据。
---

# slr-corpus-verity：题录真实性核验与语料治理

## 1. 适用场景与边界

**适用**：系统性文献综述任务中，案例随附题录清单（或经检索组装出的题录集合）
需要进入筛选流程之前；题录来源不可信（上游模型生成、多库导出合并、快照环境
离线）时尤为必要。

**边界**：
- 本 skill 的引擎只裁决**元数据层面**的可信度（schema、DOI 语法、年份、重复、
  撤稿信号），不评价文献的学术质量（那是质量评价环节的事）。
- 一切伪造嫌疑只标 `suspicious` 并附理由，**严禁**断言"伪造/fake"；最终裁量
  属于人工复核入口。
- 离线是常态：无 `--online` 时所有结论限定为"本地一致性核验"。
- 本 skill 不是"只做语料核验"：第 0 层之外，Agent 必须按第 4 节走完完整
  综述链，其余环节以 references/ 协议 + result.json 字段 + 明确的模型动作承载。

## 2. 运行环境

- 评测器将本 skill 安装至 `/skills/weekly-skill`；案例输入 `/input/case.json`
  与 `/input/task.md`，工作目录 `/app/work`，交付 `/app/output/result.json`。
- 全部脚本仅用 Python 3 标准库，支持 `--help`。
- **脚本定位兜底**（安装路径不确定时逐条执行）：

```bash
find / -maxdepth 5 -name "verify_corpus.py" -path "*corpus-verity*" 2>/dev/null
# 找到后以该文件所在目录的上一级为 $SKILL，例如：
#   /skills/weekly-skill/scripts/verify_corpus.py → SKILL=/skills/weekly-skill
```

- **退出码约定**：0=通过；2=输入/材料不足（诚实降级，仍交付协议或最小报告）；
  3=校验失败（--strict 下发现 invalid/suspicious/retraction_flagged、输出不可写、
  selfcheck 断言失败）。脚本信息输出为中文，错误带规则码（R1–R6、V1–V8）。

## 3. 工作流程（编号步骤）

> 预算纪律：64 次模型请求 / 900 秒 / 响应 16384 tokens。一切可确定性做的事
> （解析、核验、计数、骨架渲染）交给脚本；模型只做判断、解读与写作。
> **第 2 步必须把 result.json 骨架落盘**，之后各环节只增量填充。

**步骤 0｜读案例**：通读 `/input/case.json` 与 `/input/task.md`，确认
output_contract 与研究问题；不臆测缺失字段。

**步骤 1｜解析（脚本）**：

```bash
python3 $SKILL/scripts/parse_case.py --case /input/case.json \
  --task /input/task.md --out /app/work/case_summary.json
```

exit 2 时阅读 warnings：case.json 缺失/损坏则按降级版 summary 继续，并在
result.json.uncertainty 中如实说明。

**步骤 2｜保底脚手架（脚本，立即落盘）**：

```bash
python3 $SKILL/scripts/scaffold_result.py --summary /app/work/case_summary.json \
  --out /app/output/result.json
```

此后任何中断都有可交付物（status=draft）。

**步骤 3｜研究问题结构化拆解（模型动作）**：把研究问题拆成 PICO/SPIDER 要素
（人群、干预/暴露、对照、结局、研究设计），写入 result.json.checks.question_decomposition；
若 parse_case 标了 needs_confirmation=true，拆解前先核对 task.md 原文，确认
结果记入 change_records，仍存疑则进 uncertainty。

**步骤 4｜检索式构建（模型动作，协议化留痕）**：即使案例已给题录清单，也必须
重建"应有的检索策略"以论证语料覆盖度：数据库（如 PubMed/Embase/CNKI）、
字段（题名/摘要/主题词）、布尔逻辑（要素内 OR 同义词、要素间 AND）、同义词
与自由词、时间与语言限制；每段检索式注明**设计意图**，写入
result.json.checks.search_strategy。语料与策略的偏差（如某同义词族零命中）
写入 uncertainty。

**步骤 5｜【签名环节】第 0 层：语料核验与治理（脚本）**：

```bash
python3 $SKILL/scripts/verify_corpus.py --records <records_path> \
  --out /app/work/corpus_report.json            # 评审或高风控场景加 --strict
```

- records_path 取 case_summary.json 的 records_path_candidates 首项；候选为空
  时回到材料清单人工指认，指认不了 → 按第 6 节"records 缺失"降级。
- **铁律：任何记录未过 verify_corpus 不得进入筛选**。只有 state=verified 的
  记录进入步骤 7 的题录筛选；quarantine 清单（invalid/suspicious/
  retraction_flagged/duplicate/probable_duplicate）逐条携带 reasons。
- 隔离清单的**每条理由**写入 result.json.evidence_matrix（记录 id + state +
  reasons + 规则码）与 uncertainty（可疑项的处置建议）。
- probable_duplicate 按 references/duplicate_policy.md 第 4 节人工复核，
  结论记入 change_records。
- PRISMA 计数（identified / duplicates_removed / quarantined /
  clean_for_screening）原样抄入 result.json.counts 与 checks.prisma_flow，
  不得手工改动——改动即破坏机器可复核性。

**步骤 6｜条款化纳排标准（模型动作）**：把纳排标准写成可逐条打勾的条款
（每条含 id、条款文本、对应 PICO 要素），写入 checks.eligibility_criteria；
纳入/排除必须引用条款 id，不允许"凭感觉"。

**步骤 7｜两轮筛选留痕（模型动作）**：第一轮题录级（title/abstract）对
clean_for_screening 的记录逐条对照条款判定；第二轮全文级（PDF 用 pdftotext /
pdf-text-tool / OCR 现场解析）。两轮结果写入 evidence_matrix：每条记录一行
（id、轮次、判定、命中条款 id、依据摘录）。全文不可得按第 6 节处理，不得
直接排除而不留痕。

**步骤 8｜质量评价（模型动作，逐维度+依据）**：按研究设计选量表（RCT 用
RoB2 维度：随机化、分配隐藏、盲法、结局数据完整性、选择性报告；观察性研究
用 NOS：选择、可比性、结局/暴露）。逐维度打分并附**原文依据摘录**，写入
evidence_matrix（quality 维度行）与 checks.quality_appraisal。无全文支撑的
维度标"无法判断"并说明，禁止脑补。

**步骤 9｜综合（模型动作）**：对纳入研究做叙述性综合（异质性允许时方可
定量合并；本 skill 不做 meta 分析计算，只做结构化综合）：每条结论回链
evidence_matrix 的记录 id 与依据；显式列出**冲突证据**（结论相反的研究及其
质量差异）与**研究空白**；全部结论做**事实/推断/无法确定**三分：
直接有据=事实，逻辑外推=推断（写明推理链），证据不足=无法确定（进
uncertainty）。成品写入 result.json.product。

**步骤 10｜组装 result.json（模型动作）**：在骨架上增量填充全部合同字段
（映射见第 4 节），status 由 draft 改为 complete/partial/failed（附原因），
change_records 记录每个环节的增量修改。

**步骤 11｜自查（脚本+模型）**：运行第 7 节自查清单与
`python3 $SKILL/scripts/selfcheck`（对 examples，不影响案例产物）；逐项核对
output_contract 字段齐备、PRISMA 计数与 corpus_report.json 一致、隔离理由
均已入 evidence_matrix。

## 4. 输出合同映射表（result.json 每个字段从哪来）

| 字段 | 来源 |
|---|---|
| case_id | case_summary.json.case_id（parse_case.py） |
| skill_name | 固定 "slr-corpus-verity"（scaffold_result.py） |
| status | 模型在步骤 10 置 complete/partial/failed+原因（骨架默认 draft） |
| product | 步骤 9 综合结论（事实/推断/无法确定三分 + 证据回链） |
| evidence_matrix | 步骤 5 隔离理由行 + 步骤 7 筛选行 + 步骤 8 质量评价行 |
| sources | 步骤 7–9 实际使用的记录 id 与材料文件清单 |
| uncertainty | needs_confirmation 研究问题、伪造嫌疑处置、probable_duplicate 复核遗留、检索偏差、离线核验边界、无法判断项 |
| change_records | 步骤 3–10 每次增量填充与人工复核改判的留痕 |
| counts | corpus_report.json.prisma 原样 + 两轮筛选/纳入计数 |
| checks | question_decomposition、search_strategy、eligibility_criteria、prisma_flow、quality_appraisal、selfcheck 结果 |
| 合同扩展字段 | 按 scaffold 占位类型填充；填充不了的置 null 并在 uncertainty 说明，禁止编造 |

## 5. 异常处理（逐条处置）

| 异常 | 处置 |
|---|---|
| **records 缺失/损坏** | verify_corpus.py exit 2（R1/R2 规则码），写出最小报告；诚实降级：status=partial，只交付检索策略、纳排条款与协议（product 注明"语料不可用，以下为协议层交付"），绝不编造题录 |
| **全部记录被隔离** | status=partial，product 说明"可信语料层为空"，counts 如实（clean_for_screening=0），筛选/质量评价/综合环节标注"无记录可评"，并在 uncertainty 列出逐条隔离理由与恢复路径（人工复核入口） |
| **检索为空**（重建策略下某要素零命中） | 检查同义词族与字段限定是否过严，放宽一轮并留痕；仍为空则在 product 写明"当前语料对该要素无证据"，进研究空白，不扩写结论 |
| **数据库或接口超时 / 联网超时** | --online 下 V8 自动降级：online_check=unavailable，online_errors 留痕，exit 码不受影响；result.json 注明"结论为本地一致性核验"，绝不把"快照中查不到"当伪造证据 |
| **全文不可得** | 该记录题录轮判定保留、全文轮标"全文不可得"，质量评价对应维度标"无法判断"；进 uncertainty；不得直接排除而不留痕 |
| **术语同义歧义** | 检索式的同义词族显式列全（含缩写、商品名/通用名、中英文），歧义词在 checks.search_strategy 中注明取舍理由；残余歧义进 uncertainty |
| **纳排条款冲突** | 两条款对同一记录给出相反判定时，以更保守（排除倾向）条款为准并在 change_records 记录冲突与裁决理由；无法裁决则该记录标"待定"进 uncertainty |
| **纳入证据互相矛盾** | 不强行调和：在 product 的"冲突证据"小节并列呈现，按质量评价结果分层讨论，结论降级为推断或无法确定 |
| **权限不足**（/app/output 不可写等） | 脚本 exit 3（R3）；改写到 /app/work 并在最终答复中显式说明交付物实际路径 |
| **超时风险**（900 秒预算） | 优先级：result.json 骨架 > corpus_report > evidence_matrix > product 文字；放弃 --online、压缩叙述篇幅，保机器可复核制品完整 |

**DOI 合法但疑似伪造**：V2 只能管语法；语法合法而内容可疑（如注册段罕见、
与 venue 不匹配）的记录只能标 suspicious 并写清疑点，**不能断言伪造**，
交人工复核并在 uncertainty 跟踪。

## 6. 自查方法

1. `python3 $SKILL/scripts/selfcheck` → 必须 exit 0（38 项断言：py_compile、
   正例逐条状态、--strict exit 3、损坏/缺失输入 exit 2、解析与骨架链路）。
2. 对案例产物逐项核对：
   - result.json 含 output_contract **全部**字段；status 非 draft；
   - counts.prisma 与 /app/work/corpus_report.json.prisma **逐数一致**；
   - quarantine 每条记录在 evidence_matrix 中有对应行且 reasons 非空；
   - product 每条结论有 evidence_matrix 回链 id；事实/推断/无法确定三分齐全；
   - uncertainty 非空时每条均可追溯到具体环节；无编造文献元数据。
3. 重跑一次 verify_corpus.py，比对两次 corpus_report.json 的 records 段
   （generated_at 除外）应完全一致——确定性是机器可复核的前提。

## 7. 最小调用示例（可直接复制执行）

```bash
# 定位 skill（安装路径不确定时）
find / -maxdepth 5 -name "verify_corpus.py" -path "*corpus-verity*" 2>/dev/null
SKILL=/skills/weekly-skill   # 按上一步结果调整为其上一级目录

mkdir -p /app/work /app/output
# 1) 解析案例
python3 $SKILL/scripts/parse_case.py --case /input/case.json \
  --task /input/task.md --out /app/work/case_summary.json
# 2) 保底骨架立即落盘
python3 $SKILL/scripts/scaffold_result.py --summary /app/work/case_summary.json \
  --out /app/output/result.json
# 3) 第 0 层语料核验（签名环节；离线默认，可联网时追加 --online）
python3 $SKILL/scripts/verify_corpus.py \
  --records "$(python3 -c "import json;print(json.load(open('/app/work/case_summary.json'))['records_path_candidates'][0])" 2>/dev/null || echo /input/records.json)" \
  --out /app/work/corpus_report.json --strict
# 4) 自检（任何时候都可跑，验证 skill 完整性）
python3 $SKILL/scripts/selfcheck
```

随后 Agent 按第 3 节步骤 3–11 增量填充 /app/output/result.json 直至交付。
