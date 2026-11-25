---
name: patent-chronology-semantics-engine
description: 当任务涉及专利或技术文献中的日期解析与时间口径工程时使用——包括异构日期格式（ISO 8601、"Jun. 5, 2018"、6/5/2018、2018年6月5日、紧凑 20180605、OCR 错乱变体）的确定性归一化（带精度标志、逐字引文锚点与格式标签）、日期口径的严格区分（优先权日/申请日/公开日/授权日/论文上线与见刊日期，绝不混淆优先权与申请）、带日期的著录事件抽取、逐案时间轴构建与事件顺序冲突检测（如授权早于申请）、观测同族优先权一致性核查，以及带硬性护栏的法定参考日期估算（20 年保护期、美国维持费 3.5/7.5/11.5 年窗口；一律标记 is_estimate 与非法律状态、附假设清单与 as-of 基准日，绝不输出法律状态结论）。
---

# patent-chronology-semantics-engine（日期口径与时间轴工程）

## 一、用途与适用条件

本技能的唯一焦点是**时间**：对专利记录、影印件著录文本与技术文献中出现的异构日期做确定性解析、归一化与口径管理，并在此基础上构建时间轴、检测时序冲突、核查观测同族优先权一致性、生成带硬性护栏的法定参考日期估算。

适用条件（同时满足）：

1. 输入为可读取的文本（专利记录文本、OCR 文本、JSON 记录）；影印件 PDF 须先由环境完成 OCR/文本层提取，本技能只消费其文本产物。
2. 任务问题涉及日期本身：日期归一化、口径区分、时序核查、同族优先权一致性、法定参考日期估算。
3. 需要**可审计**的输出：每个解析结果必须携带逐字引文（quote）、字符区间（span）、格式标签（format_tag）与精度标志（precision）。

核心语义纪律：

- 日期口径严格分离：`priority`（优先权日）≠ `filing`（申请日）≠ `publication`（公开日）≠ `grant`（授权日）；论文另有 online / print 日期，亦不得混入专利口径。**把优先权日当作申请日（或反之）是错误。**
- 一切估算（20 年保护期、维持费窗口）仅是**日期推算参考**：输出必含 `is_estimate=true`、`not_legal_status=true`、`assumptions[]`、`as_of`。**本技能永不输出法律状态结论；官方法律状态未知时，必须如实说明。**

## 二、运行时契约（评测环境）

1. 评测方将本技能安装于 `/skills/weekly-skill`，并以官方 DeepSeek Harness 运行 3 个固定隐藏案例。
2. 输入位于 `/input/`：`case.json` + `task.md` + 材料文件（6 篇专利记录文本、3 份 USPTO 影印件 PDF 原件、对比论文；含按号码/按主题的查询；含来源定位的权利要求版本；**官方法律状态未知——必须如实陈述**；观测到的链接不构成完整同族；WO 合并 OCR 的边界保留原样）。
3. **必须读取真实文件内容，绝不从文件名推断。** 影印件 PDF 若无法提取文本，如实记录为限制，不得编造其内容。
4. 工作目录 `/app/work`；交付物 `/app/output/result.json`，其中：
   - `case_id`：逐字复制；
   - `status`：诚实取值 `ok` / `partial` / `failed`；
   - `sources`：每个输入文件的路径 + sha256；
   - `uncertainty`：不确定性说明；
   - `change_records`：增量修改记录；
   - **逐字段镜像 output_contract 的全部字段**；未填写的字段置 `null` 并在 `uncertainty` 中说明原因。
5. 预算：64 次请求 / 900 秒 / 16384 tokens。**先写诚实的部分骨架（skeleton）result.json，再增量改进，每次改进追加 change_records。**
6. 绝不编造；部分完成（partial）必须具名说明限制。

## 三、调用方式（有序流水线，含具体命令）

以下命令默认在技能安装目录执行（评测环境为 `/skills/weekly-skill`）。

```bash
cd /skills/weekly-skill

# 第 0 步：先写诚实的部分骨架 result.json（status=partial，全字段镜像、未填为 null），
# 之后每完成一轮改进就重写并追加 change_records。

# 第 1 步：单日期归一化（排查具体字符串时使用）
python3 scripts/date_norm.py "Jun. 5, 2018"
python3 scripts/date_norm.py "2O18-06-05"                                   # 默认 keep-raw：保留原文 + 告警
python3 scripts/date_norm.py "2O18-06-05" --ocr-policy fix-digit-confusion  # 仅当确证 OCR 来源时显式启用

# 第 2 步：逐条记录抽取带口径的日期事件（text 或 JSON）
python3 scripts/event_extract.py /app/work/rec_A.txt -o /app/work/rec_A_events.json
# OCR 文本层质量差时，可对同一份记录各跑一次两种策略并人工比对：
python3 scripts/event_extract.py /app/work/rec_A.txt --ocr-policy fix-digit-confusion \
    -o /app/work/rec_A_events_ocrfix.json

# 第 3 步：构建时间轴 + 检测顺序冲突（退出码 1 表示发现冲突，属正常产出）
python3 scripts/timeline_build.py --events /app/work/rec_A_events.json /app/work/rec_B_events.json \
    -o /app/work/timelines.json

# 第 4 步：观测同族优先权一致性核查（把观测到主张同一优先权的成员一并传入）
python3 scripts/timeline_build.py --events /app/work/rec_A_events.json /app/work/rec_C_events.json \
    --family -o /app/work/family.json

# 第 5 步：法定参考日期估算（护栏强制：必须声明 as_of；输出必带 is_estimate/not_legal_status/assumptions）
python3 scripts/term_estimate.py --request /app/work/estimate_request.json -o /app/work/estimate.json
python3 scripts/term_estimate.py --self-test   # 验证措辞护栏

# 第 6 步：汇总 sources（路径 + sha256）
python3 - <<'EOF'
import hashlib, glob, json
print(json.dumps({p: hashlib.sha256(open(p,'rb').read()).hexdigest()
                  for p in sorted(glob.glob('/input/*'))}, indent=2))
EOF

# 第 7 步：自查
python3 scripts/selfcheck.py
```

## 四、输入输出解释

| 脚本 | 输入 | 输出（要点） | 退出码 |
| --- | --- | --- | --- |
| `date_norm.py` | 单个日期字符串 | `{raw, iso, precision(day/month/year), format_tag, interpretations[], warnings[]}` | 0 解析成功（含歧义）/ 1 无法解析（保留原文）/ 2 用法错误 |
| `event_extract.py` | 专利记录 .txt 或 .json（`{"record_id","text"}`、列表或 `{"records":[...]}`） | `{"records":[{record_id, events:[{event_id, kind, raw, iso, precision, format_tag, interpretations, quote, span, context, warnings}], warnings}]}`；kind ∈ priority/filing/publication/grant/unknown | 0 正常 / 1 输入失败 / 2 用法错误 |
| `timeline_build.py` | 若干 event_extract 输出 JSON | `{timelines, conflicts[], family_check, order_baseline}`；冲突为结构化记录（`order_violation`、`family_priority_conflict`） | 0 无冲突 / 1 检出冲突（冲突已写入输出）/ 2 用法错误 |
| `term_estimate.py` | 请求 JSON 或命令行参数（`earliest_filing` 必填、`grant_date` 可选、`as_of` **必填**） | 估算 JSON：`is_estimate=true`、`not_legal_status=true`、`assumptions[]`、`as_of`、`estimates{estimated_20y_term_end, us_maintenance_windows}` | 0 正常 / 1 护栏触发（无 as_of、日期不可用、命中禁用措辞）/ 2 用法错误 |
| `selfcheck.py` | 无（使用 `examples/fixtures`） | 逐项 PASS/FAIL + 摘要 | 0 全部通过 / 1 存在失败 |

## 五、异常处理（强制纪律）

1. **无法解析的日期**：保留原文 `raw`，`iso=null`，附 `UNPARSEABLE_DATE_KEPT_RAW` 警告；`date_norm.py` 以退出码 1 标示。**绝不猜测。**
2. **歧义数字日期**（如 `03/04/2018`）：同时给出美式 M/D/Y 与欧式 D/M/Y **两种解释**并附 `AMBIGUOUS_NUMERIC_DATE` 警告；**绝不静默取舍**。时间轴排序暂按首个解释进行，但保留全部解释并附 `AMBIGUOUS_EVENT_ORDERED_BY_PRIMARY` 警告。
3. **OCR 错乱日期**（如 `2O18-06-05`）：默认 `keep-raw` 策略——保留原文 + `SUSPECTED_OCR_DIGIT_CONFUSION` 警告；仅当确证来源为 OCR 扫描件时，显式声明 `--ocr-policy fix-digit-confusion`，修复结果带 `ocr_fixed:` 前缀标签与 `OCR_DIGIT_CONFUSION_FIXED` 警告（修复仅为工作假设）。
4. **无法归类的日期字符串**：`kind=unknown` + `UNKNOWN_EVENT_KIND` 警告；unknown 事件不参与顺序冲突检测。
5. **事件顺序冲突**（如授权日早于申请日）：生成 `order_violation` 结构化冲突记录，`resolution: none`，**绝不静默修正**。
6. **观测同族优先权不一致**：生成 `family_priority_conflict`；一致则报告 `family_priority_consistent`，并注明“观测链接不构成完整同族，结论仅限观测范围”。
7. **估算护栏**：未声明 `as_of` 一律拒绝（退出码 1）；输出生成后扫描禁用措辞（如“已失效”“expired”“lapsed”“in force”），命中即拒绝输出。

## 六、限制

1. **本技能不做**：影印件 PDF 取证（字体/元数据/图像层分析）、权利要求文本比对（claim diffing）、实体消歧（申请人/发明人归一）、预算或任务调度。这些属于其他技能/环节，本技能仅消费其文本产物。
2. 正则文法表不覆盖全部人类日期写法；未命中即“无法解析并保留原文”，这是设计使然，优于误解析。
3. 类型判定基于邻近关键词启发式（前 120 字符、句/行边界截断、就近命中），非常规行文可能归为 `unknown`；`unknown` 是诚实的输出，不是缺陷。
4. 顺序基线 `priority ≤ filing ≤ publication ≤ grant` 是核查启发式而非法律推定；个别程序（如部分继续案、补正）可能存在合法例外，冲突记录须人工回查来源。
5. 估算结果仅反映所声明输入的算术推算；官方登记事实（缴费、放弃、PTA/PTE 等）不在本技能获取范围之内，故**任何情况下都不得把估算输出表述为法律状态**。
6. 跨精度比较（年/月级 vs 日级）按较低精度截断并在冲突记录中注明。

## 七、自查方法

1. 运行 `python3 scripts/selfcheck.py`：应输出 `27/27 checks passed` 并以退出码 0 结束。覆盖：各格式解析、歧义双解释、OCR 两种策略、unknown 事件、顺序冲突、同族冲突、估算护栏、缺少 as_of 拒绝、禁用措辞扫描。
2. 人工抽查要点：
   - 每个事件的 `quote` 是否与源文本逐字一致、`span` 是否指向该引文；
   - `priority` 与 `filing` 是否被严格区分（不得把优先权文本错配给申请日）；
   - 歧义日期是否同时保留两种解释；
   - 估算输出是否同时满足 `is_estimate=true`、`not_legal_status=true`、`assumptions` 非空、`as_of` 已声明；
   - `result.json` 是否逐字段镜像 output_contract，`status` 是否诚实，限制是否具名。
