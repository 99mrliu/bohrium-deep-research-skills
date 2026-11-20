---
name: identitymerge-dedup-engine
description: >
  多数据库联合检索案例中的论文身份去重与确定性合并。当案例提供 Crossref /
  EuropePMC / 出版商等多来源原始响应（外加引用图、本地导入状态）并要求产出
  去重后的 canonical 记录时使用：格式嗅探归类（crossref/europepmc/publisher/
  recordlist/jsonl/csv/reference_graph/import_state/unknown，失败降级留痕不
  静默）、统一中间格式（区分 missing/unknown/not_provided 三级缺失语义，
  容 HTML 标签与 list/dict 变体）、分层身份匹配（Tier1 标识符精确：DOI 小写
  归一、PMID/PMCID 精确、仅凭引用图显式别名的跨标识符互链绝不臆造映射；
  Tier2 归一题名+年份+首作者姓；Tier3 Jaccard≥0.6 且作者姓重合≥0.5 且
  年份差≤1 的模糊对只进仲裁队列绝不自动合并）、可解释判定日志（每条
  {pair, tier, match, reason_code, evidence}）、按每字段优先级策略的确定性
  合并（字段级 provenance 可回链、conflict_log 全留痕、按归一 DOI 或归一
  题名字典序排序可重放）。差异化能力：根治"重复判定无理由、合并取值无
  来源、结果不可复算"的失败链。边界：不联网执行真实检索（材料缺失时
  status=partial 并如实声明）、不臆造 pmid↔doi 映射、不做全文质量评价、
  不预置案例答案、模糊对裁决属模型职责不外包给脚本阈值。
---

# identitymerge-dedup-engine — 论文身份去重与确定性合并

## 1. 适用场景与边界

**适用**：`/input/case.json` + `task.md` 案例中，材料包含 ≥2 个来源的文献
记录响应（Crossref works、EuropePMC resultList、出版商 JSON/HTML/JSONL/CSV、
预处理 record 列表），可选含引用图（reference graph）与本地增量导入状态；
任务要求去重并合并为 canonical 记录，且要求判定可解释、合并可溯源、
结果可重放。

**边界（不做什么）**：
- 不联网：一切证据来自本地材料；任一来源缺失即如实 partial，不假装检索。
- 不臆造跨标识符映射：PMID-only × DOI-only 的互链只能依据引用图/映射表
  显式别名（`T1_ID_CROSSREF`），无别名则走 Tier2/Tier3 书目证据。
- 不做全文质量评价、不做检索式工程、不做覆盖审计（属其他方向）。
- 不预置案例答案；examples/ 全部为合成虚构数据。
- Tier3 模糊对脚本只排队，裁决是模型职责（写 rationale），不得调阈值
  强并。

## 2. 运行环境

- 全部脚本 Python 3 标准库，位于本 skill 的 `scripts/` 下，支持 `--help`。
- 定位兜底（安装路径不确定时）：
  `find / -maxdepth 5 -name "dedup.py" -path "*identity-merge*" 2>/dev/null`
  找到后以该目录的上级为 `$SKILL`；SKILL.md 可搜 `"identitymerge-dedup-engine"`。
- 退出码约定：0=通过；2=输入/材料不足（诚实降级）；3=校验失败/输入非法。
  所有脚本顶层 try/except 兜底：未预期异常汇总后 exit 2，绝不 crash。
- 中间产物在 `/app/work`，最终交付 `/app/output`；所有脚本幂等，
  同参数重跑覆盖同名产物，支持断点续跑。

## 3. 工作流程（编号步骤）

预算适配：64 请求 / 900s。步骤 0–2 与 3–4、6、8 全部脚本化（每步一次
bash 请求内可串行多条命令）；唯一重判断环节是步骤 5 仲裁，**一次请求
批量裁决**；步骤 7 组装 result.json。任何时刻中断，`/app/output/result.json`
骨架与已完成的 work 产物即为可交付状态。

0. **读案例（模型）**：通读 `/input/case.json` 与 `/input/task.md`。
1. **解析嗅探**：`python3 $SKILL/scripts/parse_case.py` →
   `/app/work/case_summary.json`。检查 `source_dbs`、
   `reference_graph_files`、`import_state_files`、`unparsed_files`；
   研究问题若取自 task.md 会标 `needs_confirmation`，须记入
   change_records 二次确认。
2. **保底脚手架**：`python3 $SKILL/scripts/scaffold_result.py` →
   `/app/output/result.json` 骨架落盘，之后全程增量填充，防超时零交付。
3. **归一化**：`python3 $SKILL/scripts/normalize_records.py --summary
   /app/work/case_summary.json` → `/app/work/normalized.jsonl`。exit 2
   表示无记录型材料：如实降级，跳到步骤 7 填 status=partial/failed。
   浏览 `parse_warnings` 与字段 `status`，确认 missing/unknown/
   not_provided 分布合理。
4. **分层去重**：`python3 $SKILL/scripts/dedup.py --normalized
   /app/work/normalized.jsonl --summary /app/work/case_summary.json` →
   `dedup_decisions.jsonl`（可解释判定）、`clusters.json`、
   `arbitration_queue.json`。抽查：T1_ID_CROSSREF 条目的
   alias_source_files 非空；NON_DUP_YEAR_MISMATCH 是否为版本差异误判。
5. **仲裁（模型判断，唯一重判断环节）**：参照
   `templates/arbitration_queue.md`，对队列中每条 pending 写决议到
   `/app/work/arbitrations.json`（decision merge/split + 必填 rationale）；
   逐条登记 change_records。证据不足一律 split 并记 uncertainty。
   队列为空则跳过。
6. **确定性合并**：`python3 $SKILL/scripts/merge_records.py --normalized
   /app/work/normalized.jsonl --clusters /app/work/clusters.json
   [--arbitrations /app/work/arbitrations.json]` →
   `/app/work/merged_records.json` + `conflict_log.jsonl`。无仲裁文件时
   模糊簇保持 `pending_arbitration` 并如实标注。审 conflict_log：
   标识符冲突（rule=identifier_priority）必须进 uncertainty 复核。
7. **组装 result.json（模型）**：按第 4 节映射填充；product 指向
   merged_records.json、dedup_decisions.jsonl、conflict_log.jsonl、
   arbitration_queue/arbitrations 路径；counts 填 input_records/
   canonical_records/冲突数/待仲裁数；status 诚实（存在未决仲裁或
   unparsed_files 非空 → partial）。
8. **自查**：`python3 $SKILL/scripts/selfcheck`，exit 0 后把结果记入
   result.json.checks；非 0 按输出定位修复后重跑。

断点续跑：步骤 1–8 幂等；中断后从最后一个未完成的编号步骤重跑即可，
scaffold_result.py 默认不覆盖已有 result.json。

## 4. 输出合同映射（result.json 字段来源）

| 字段 | 来源 |
|---|---|
| case_id | case_summary.json |
| skill_name | 固定 `identitymerge-dedup-engine` |
| status | complete / partial / failed + reason；未决仲裁、unknown 文件、任一来源缺失 → partial |
| product | merged_records.json（canonical 记录+field_provenance）+ dedup_decisions.jsonl + conflict_log.jsonl + arbitration 文件路径 |
| evidence_matrix | 判定日志按 reason_code 汇总 + 每簇 tier/status |
| sources | case_summary.materials（文件名+嗅探类型+用途+路径定位） |
| uncertainty | 未决仲裁对、标识符冲突、missing/unknown 字段清单、unparsed_files、未验证假设 |
| change_records | 脚手架初始化、每条仲裁决议、task.md 取题二次确认、阈值改动 |
| counts | input_records / canonical_records / auto / resolved / pending / conflicts |
| checks | parse/normalize/dedup/merge/selfcheck 的 exit 码与摘要 |

output_contract 中超出上表的字段：scaffold_result.py 已生成占位，按案例
语义填充；合同与默认字段冲突时以合同为准并记 change_records。

## 5. 异常处理

| 异常 | 处置 |
|---|---|
| 材料为零 / case+task 均缺 | parse_case.py exit 2；result.json status=failed，不伪造记录 |
| 文件无法归类（坏 JSON、未知 schema） | 降级 unknown 记入 unparsed_files，parse 仍 exit 0；绝不静默吞掉；normalize 跳过 |
| 记录型材料为空 | normalize_records.py exit 2；status=partial 并说明 |
| 字段缺失 | 三级语义区分：missing（所有来源无此字段）/ unknown（有键但空或不可解析）/ not_provided（schema 无此键），写入 field_status 与 provenance，不编造填补 |
| 标识符冲突（同簇多个 DOI） | conflict_log rule=identifier_priority，取优先级值、全值留痕、进 uncertainty 复核 |
| 年份冲突的同题名对 | NON_DUP_YEAR_MISMATCH 自动拒并（年度综述场景）；如判系版本差异，模型仲裁 merge 覆盖并写 rationale |
| 模糊相似对 | 一律 T3_FUZZY_ARBITRATE 进队列；无仲裁文件则 pending 标注，status 不得 complete |
| 引用图缺失/非法 | dedup 仅失去 T1_ID_CROSSREF 证据，WARN 留痕继续；跨标识符对降级 Tier2/3 |
| 撤回/勘误标记 | 本 skill 不做判定；材料中如有相关字段，原样保留进 provenance 并记 uncertainty |
| 超时 | 步骤 2 骨架 + 已完成 work 产物即为可交付；合并未跑则 product 指 normalized.jsonl 与判定日志并 status=partial |

## 6. 自查方法（selfcheck）

```bash
python3 $SKILL/scripts/selfcheck    # 或 chmod +x 后直接执行
```

跑 `examples/` 下合成示例（全部虚构数据，见 examples/README.md）：正例
全链路 parse→scaffold→normalize→dedup→merge exit 0，并断言：已知 DOI
重复对归并（T1_DOI_EXACT）、跨标识符互链对归并（T1_ID_CROSSREF，仅凭
引用图显式别名）、无标识符同题名对 Tier2 归并、同题名不同年份不并
（NON_DUP_YEAR_MISMATCH）、T3 模糊对进仲裁且不自动并、作者串
`Surname I.` 与 `Family, Given` 两格式解析一致、missing/unknown/
not_provided 语义正确、无仲裁文件时 pending 如实标注、仲裁决议应用后
resolved_by_arbitration、两次 merge 输出逐字节一致（确定性）、冲突日志
含预埋 issue 冲突；降级断言：空材料 exit 2、坏 JSON 不崩溃且入
unparsed_files、缺输入 exit 2、坏行留痕；全部脚本 py_compile。
任一断言失败 selfcheck 以 exit 3 结束。

## 7. 最小调用示例（示例输出，非真实案例结果）

```bash
SKILL=$(dirname $(dirname $(find / -maxdepth 5 -name "dedup.py" -path "*identity-merge*" 2>/dev/null | head -1)))
mkdir -p /app/work /app/output
python3 $SKILL/scripts/parse_case.py --case /input/case.json --task /input/task.md \
    --out /app/work/case_summary.json
python3 $SKILL/scripts/scaffold_result.py --summary /app/work/case_summary.json \
    --out /app/output/result.json
python3 $SKILL/scripts/normalize_records.py --summary /app/work/case_summary.json \
    --out /app/work/normalized.jsonl
python3 $SKILL/scripts/dedup.py --normalized /app/work/normalized.jsonl \
    --summary /app/work/case_summary.json \
    --decisions /app/work/dedup_decisions.jsonl \
    --clusters /app/work/clusters.json --queue /app/work/arbitration_queue.json
# （模型批量裁决后写出 /app/work/arbitrations.json；无待裁项可省略）
python3 $SKILL/scripts/merge_records.py --normalized /app/work/normalized.jsonl \
    --clusters /app/work/clusters.json \
    --arbitrations /app/work/arbitrations.json \
    --out /app/work/merged_records.json --conflicts /app/work/conflict_log.jsonl
python3 $SKILL/scripts/selfcheck
```

合成示例上的期望合并输出片段见 `examples/expected_merged.example.json`
（11 条 canonical 中的 W001/W003 两条，含 field_provenance 与冲突样例；
虚构数据，仅演示输出形状）。
