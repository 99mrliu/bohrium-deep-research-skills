---
name: query-orchestration-planner
description: 多数据库联合检索的"上游查询编排与来源调度"技能——负责记录被合并之前的一切。何时使用:当任务给出 Crossref/EuropePMC/出版方等离线响应材料并要求联合检索时,在一切去重、合并、统计之前,先把研究问题翻译成尊重各库查询语法、字段能力、分页方式与配额的逐库查询计划。做什么:结构嗅探每份材料(crossref 信封/europepmc resultList/出版方 json|jsonl|csv/引用图/增量导入状态/未知隔离);接收模型抽取的中性 facet 概念块(facets.json,单次批量);脚本编译 query_plan.json(逐库适配查询串、分页策略、页大小、排序、配额/重试/超时、覆盖角色与降级链);再把计划与实际在场的材料响应对账——核对查询回响(query echo,matched/mismatched/not_echoed)、检测单页截断(Crossref total-results vs items、EuropePMC hitCount vs result),响应缺失的数据库在 coverage_declaration.json 与 query_ledger.jsonl 中显式声明覆盖缺口,绝不静默跳过或臆造结果。差异化能力:其他技能默认"材料齐全",本技能把"计划 vs 实到材料"的对账作为一等公民——缺口是显式产物而非异常。边界:不联网、不臆造任何库的响应、不做去重/合并/覆盖统计等下游处理;契约字段无法确定性填充时置 null 并登记 unresolved,状态诚实标注 complete/partial/failed。Python 3 标准库、离线、确定性、幂等、退出码 0/1/2/3。
---

# query-orchestration-planner:多数据库联合检索的上游查询编排与来源调度

## 适用场景与边界

**何时使用**:任务给出多个文献数据库的**离线响应材料**(Crossref works 信封、
EuropePMC resultList、出版方 JSON/JSONL/CSV、引用图、组织方增量导入状态),
要求在**合并任何记录之前**完成:研究问题 → 逐库查询计划(语法/字段/分页/配额
各自适配)→ 计划与实到材料对账 → 覆盖缺口显式声明。凡需要回答"每个库*应该*
怎么查、*实际*查到了什么、*缺了*哪个库"的情形,均属本技能。

**边界(严格遵守)**:

- **不联网**:评测环境无网络;本地材料即各库响应,绝不调用实时 API。
  `references/db-capabilities.md` 仅为规划笔记。
- **不臆造响应**:任何库的响应缺失时,只登记 gap,绝不编造记录补齐。
- **材料缺失即诚实 partial**:缺口、截断、未知格式全部进入
  `coverage_declaration.json` 与 `result.json.uncertainty`,status 降级。
- **不做下游**:不去重、不合并、不做覆盖矩阵统计、不抽取证据、不写综述;
  这些字段在契约中只能置 `null` 并登记 unresolved。
- **不臆造 facets**:facets 是模型判断的产物;缺失时脚本以退出码 2 降级,
  绝不自行编造研究切面。

## 运行环境

- Python 3,**仅标准库**(argparse/json/csv/hashlib/re/os/io/sys);无第三方依赖。
- 平台安装路径 `/skills/weekly-skill`;若不确定,回退定位:
  `find / -maxdepth 6 -name "query_planner.py" 2>/dev/null`,
  取其上两级为 `$SKILL`。
- 退出码:`0`=正常(允许 status=partial 的诚实结果);`1`=自查未通过;
  `2`=材料不足诚实降级(如 facets.json 缺失、无任何在场材料);
  `3`=输入非法(case.json 缺失/不可解析/缺 case_id)。
- 脚本**幂等且确定性**:无墙钟、无随机、产物排序落盘;同输入重跑字节一致。
  顶层 try/except 兜底,任何异常不裸崩溃,尽量留下 status=failed 的 result.json。

## 运行契约

- 输入(只读):`/input/case.json`、`/input/task.md`、`/input/materials/*`。
- 中间产物:`/app/work`(case_summary / facets / query_plan /
  coverage_declaration / query_ledger / candidate_pool / stage_checks /
  selfcheck_report)。
- 交付:`/app/output`,其中 `result.json` **必须**包含 `case_id` 以及
  `case.json.output_contract` 声明的**每一个字段**(顶层展开);无法确定性
  填充的字段置 `null` 并登记入 `unresolved` 列表(含原因);`status` 取值
  `complete`(全部计划库在场、无截断、契约全填充)/`partial`(存在缺口、
  截断或未决字段,原因写入 `status_reason`)/`failed`(输入非法)。

## 工作流程

0. **(脚本)读取 case+task**:`run-all` 内部先校验 case.json 合法性;
   非法即写最小 result.json(status=failed)并以退出码 3 结束。
1. **(脚本)parse 嗅探材料**:逐文件结构嗅探(crossref / europepmc /
   publisher_json|jsonl|csv / reference_graph / import_state / unknown),
   记录 `{path, sha256, bytes, sniffed_type, record_count,
   truncation_detected}`——Crossref 比较 `total-results` 与 `len(items)`,
   EuropePMC 比较 `hitCount` 与 result 数;未知类型**隔离登记**而非丢弃;
   声明而缺失、磁盘多出的未声明文件均显式列出 → `case_summary.json`。
2. **(脚本)早期骨架**:`case_summary.json` 一旦写出即构成诚实中间态;
   finalize 在任何后续失败下仍能以 partial/failed 汇总,不留空目录。
3. **(模型,唯一判断点,单次批量)抽取 facets**:代理通读 case.json 的
   research_question 与 task.md,**一次请求**产出 PICO 式中性概念块写入
   `/app/work/facets.json`(模式见 `references/query-grammar.md`)。
   预算上仅此 1 次模型请求;脚本不参与语义判断。
4. **(脚本)plan 编译逐库计划**:对 case.json `source_dbs` 中**每个**库
   (缺省 {crossref, europepmc, publisher})生成:适配语法的查询串
   (Crossref `query.bibliographic` + `filter=from-pub-date/.../type`;
   EuropePMC `TITLE_ABS:"..." AND ... AND PUB_YEAR:[...]`,cursorMark 分页;
   publisher 仅登记中性关键词 + 站点注意事项)、分页策略、页大小、排序、
   配额/重试/超时、覆盖角色(强/弱 facet,含 EuropePMC 农学偏弱这类学科
   声明)与**降级链**(该库缺席时的结论路径) → `query_plan.json`。
   facets 缺失 → 退出码 2,明确提示由模型补齐后重跑。
5. **(脚本)reconcile 对账**:计划 vs 在场材料:逐库 `response_present`;
   在场则核对查询回响(Crossref `message.query` / EuropePMC
   `request.queryString`)与计划意图的词重合度 → `matched / mismatched /
   not_echoed`(回响缺失不是错误但降置信);缺席则生成 gap
   `{db, planned_query, impact(哪些 facet 失去覆盖), declaration}`。
   产出 `coverage_declaration.json` 与 `query_ledger.jsonl`
   (每行一条计划/执行查询:参数、分页、回响状态、结果计数、截断标记);
   同时从在场响应登记**未去重**候选标识 `candidate_pool.json`。
6. **(模型,可选,1 次)复核缺口报告**:代理通读 coverage_declaration,
   确认 gap 声明与 task 预期一致,决定接受缺口或请求补采;不改变脚本产物,
   仅在 result.json 的 method_notes/open_questions 层面留痕。
7. **(脚本)finalize 汇总**:写出 `result.json`:case_id、skill_name、
   status+reason、product(三个产物路径)、**全部契约字段**(填充或
   null+unresolved)、sources(逐材料 sha256+嗅探类型)、uncertainty
   (缺席库/未知格式/未确认假设)、change_records、counts、checks
   (各阶段退出码)。
8. **(脚本)selfcheck**:契约完备(每个字段顶层存在)、null 与 unresolved
   双向一致、产物哈希与 work 副本一致、计数可从 case_summary 重算、
   无静默丢弃(声明+额外=登记总数)、每个 gap 库均在 uncertainty 声明、
   台账行数=计划库数;全过退出 0,否则 1。

## 输出合同映射

| 契约字段名(关键词匹配,小写包含) | 填充来源 | 备注 |
|---|---|---|
| 含 `candidate` | `candidate_pool.json` 的候选标识数组(未去重,带 source_db) | 上游登记,交下游合并 |
| 含 `coverage` | coverage_declaration 摘要 + 缺口库列表 + 截断标记 | |
| 含 `ledger` | `"query_ledger.jsonl"` 指针 | |
| 含 `plan` | `"query_plan.json"` 指针 | |
| 含 `question` | 由 gap/截断派生的遗留问题数组 | |
| 含 `status` | `{status, status_reason, checks}` 状态报告 | |
| 含 `method`/`note` | 方法说明字符串(流程与边界) | |
| 含 `evidence`/`merged`/`dedup`/`answer`/`synthesis` | **一律 null + unresolved** | 下游职责,禁止臆造 |
| 其他任意名 | null + unresolved(原因"无确定性映射") | 禁止捏造 |

## 异常处理表

| 异常 | 处置 |
|---|---|
| case.json 缺失/不可解析/缺 case_id | 退出码 3;尽力写最小 result.json(status=failed) |
| 某库材料整体缺失(如 publisher) | 不报错中断;reconcile 生成 gap 条目,impact 列出失去覆盖的 facet;status=partial;uncertainty 登记 absent_db |
| case.json 声明但磁盘缺失的文件 | case_summary 记 `missing`;uncertainty 登记 missing_declared |
| 磁盘存在但未声明的文件 | 嗅探后以"额外材料"登记,不静默丢弃 |
| 未知/不可解析格式 | `sniffed_type=unknown/unparseable`,`quarantined=true` 隔离登记;uncertainty 登记 unknown_format |
| 单页截断(Crossref total-results>items;EuropePMC hitCount>result) | `truncation_detected=true` + detail;truncation_flags;open_questions 提示补采分页;status=partial |
| 编码异常 | 依次尝试 utf-8 → utf-8-sig → latin-1,回退时记录 `encoding_fallback`;全失败记 unparseable 隔离 |
| 查询回响缺失 | `query_echo=not_echoed`,非错误,但对账置信度降级并留痕 |
| 回响与计划意图不符(重合度<0.6) | `query_echo=mismatched`,在 coverage_declaration 告警(材料或不是本计划的响应) |
| facets.json 缺失/非法 | plan 退出码 2,提示由模型补齐;run-all 继续 finalize 为 partial |
| 能力表无此库条目 | 该库 `planned=false` + 说明,不编译、不中断 |
| 填充函数异常 | 该契约字段 null + unresolved(原因含异常),流程继续 |

## 合成最小示例

`examples/synthetic-input/`(**全部虚构**:case_id `synthetic-query-orch-001`,
主题为虚构化合物 ZK-7 对水稻根向地性的剂量效应;publisher 材料故意缺席,
Crossref 响应故意截断)。复现:

```bash
python3 /skills/weekly-skill/scripts/query_planner.py run-all \
  --input  /skills/weekly-skill/examples/synthetic-input \
  --work   /tmp/qo-work --output /tmp/qo-out \
  --facets /skills/weekly-skill/examples/synthetic-input/facets.json
# 期望 exit=0,result.status=partial(publisher 缺口 + crossref 截断均已声明)
```

`examples/synthetic-output/` 为真实执行产物;命令、退出码与观察记录见其中
`run-record.md`。分步调试:依次 `parse` →(模型写 facets)→ `plan` →
`reconcile` → `finalize` → `selfcheck`,每步退出码独立可查。

## 诚实与约束声明

- 本技能的一切结论仅来自**离线材料 + 查询计划的对账**;不访问网络、不臆造
  任何数据库的响应内容;材料缺失时唯一合法动作是**声明缺口并降级**。
- 语义判断仅一处(facets 抽取,单次批量模型请求);脚本侧无任何启发式编造,
  阈值(回响重合度 0.6)公开于 `references/db-capabilities.md`。
- 候选集是**未去重的原始登记**,专为下游去重/合并技能设计;本技能输出不含
  任何合并结论。
- 确定性保障:无墙钟、无随机、相对路径、排序落盘;同一输入重跑产物
  字节一致。维护时若修改文法或能力表,必须同步更新两个 references 文件并
  重跑合成示例验证字节一致。
