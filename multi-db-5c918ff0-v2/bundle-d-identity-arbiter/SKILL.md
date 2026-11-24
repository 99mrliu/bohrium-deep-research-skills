---
name: identity-arbiter
description: >
  论文身份去重判定与确定性合并（多数据库联合检索场景）。当任务要求对来自 Crossref、
  EuropePMC、出版方等异构离线响应进行记录级去重，且要求"判定可解释、模糊匹配不得
  自动合并、合并值须带字段级溯源"时使用本技能。核心纪律：T1 标识符精确匹配（共享
  规范化 DOI / 共享 PMID / 仅限 reference_graph 或 import_state 显式声明的跨标识符
  别名对，绝不臆造 pmid↔doi 映射）与 T2 书目精确匹配（规范化标题+年份+第一作者姓氏
  全同）可自动合并；T3 模糊候选（标题 token Jaccard≥0.6 且姓氏重叠≥0.5 且年份差≤1）
  一律只进 arbitration_queue.json，由模型/人工一次性批量裁决后经 --adjudications 回放。
  每个候选对产出一条含 reason_code 与 evidence 的 JSONL 决策行；合并按来源优先级
  （默认 publisher > crossref > europepmc）逐字段确定性取值，分歧写入 conflict_log.json。
  边界：不做引用网络推断、不做全文相似度、不臆造缺失标识符；无法识别形状的材料一律
  隔离（quarantine）而非强解；待仲裁存在时 status=partial 并显式列入 uncertainty。
---

# identity-arbiter：论文身份去重判定与确定性合并

## 何时使用

- 多数据库联合检索后，需要判定哪些记录指向**同一篇论文**并产出规范（canonical）记录。
- 评审/交付要求去重判定**逐对可解释**（reason code + 数值证据），模糊匹配**绝不自动合并**，
  合并字段值**逐字段可溯源**且跨来源分歧留有冲突记录。
- 输入为离线材料：Crossref `{"message":{"items":[...]}}`、EuropePMC
  `{"resultList":{"result":[...]}}`、出版方 JSON 数组或 JSONL、留存的 reference_graph、
  组织方本地 import_state；形状无法识别的材料进入隔离区并在报告中声明。
- 不适用：需要联网补全元数据、需要全文/语义相似度、需要推断未声明的标识符映射的场景。

## 固定运行方式

技能安装于 `/skills/weekly-skill`。在 `/app/work` 下工作，交付 `/app/output/result.json`：

```bash
python3 /skills/weekly-skill/scripts/identity_arbiter.py \
  --case /input/case.json --task /input/task.md \
  --work /app/work --out /app/output
# 可选：应用一次性批量裁决（模型对 T3 对的裁定）
python3 /skills/weekly-skill/scripts/identity_arbiter.py \
  --case /input/case.json --task /input/task.md \
  --work /app/work --out /app/output \
  --adjudications /app/work/adjudications.json
```

若安装路径不符，回退定位：

```bash
find / -maxdepth 6 -name "identity_arbiter.py" 2>/dev/null
```

`--help` 可用；Python 3 标准库实现，无网络、无随机性、产物不含墙钟时间。

## 完整工作流

1. **STEP 0（脚本，最先执行）**：在读任何输入之前写入 `result.json` 骨架（`status="partial"`）。
2. **材料发现与嗅探分类（脚本）**：按结构嗅探 crossref / europepmc / publisher(array|jsonl) /
   reference_graph / import_state / unknown；unknown 一律隔离，绝不强解。
3. **规范化（脚本）**：DOI 小写去前缀去尾标点；PMID/PMCID 精确字符串；标题 NFC+小写+
   去标点+折叠空白；作者姓氏同时兼容 Crossref author 列表与 EuropePMC authorString；
   字段状态区分 missing / unknown / not_provided；摘要容忍 HTML 残留。
4. **分层匹配（脚本）**：见 `references/matching-rules.md`。T1/T2 自动合并；
   T3 仅入仲裁队列。每个候选对写一条 `dedup_decisions.jsonl`。
5. **T3 仲裁（模型职责，一次性批量完成）**：阅读 `arbitration_queue.json` 中每对的
   evidence（title_sim / surname_overlap / year_diff / 标题与作者原文），结合任务问题
   一次性裁定全部 T3 对，写 `/app/work/adjudications.json`
   （格式：`[{"pair":[idA,idB],"decision":"merge|separate","rationale":"..."}]`），
   再用 `--adjudications` 重跑脚本。预算意识：全程 64 次请求 / 900 秒，
   仲裁务必**一次批量裁决**，禁止逐对往返；拿不准的对判 `separate` 并写明 rationale——
   误合并的代价高于保守拆分。
6. **确定性合并（脚本）**：按 `references/merge-policy.md` 的来源优先级表逐字段取值，
   记录 `{db, artifact_id, locator}` 溯源；分歧值写入 `conflict_log.json`；
   规范记录按 (规范化 DOI 否则规范化标题) 排序，输出稳定可回放。
7. **报告与交付（脚本）**：`identity_report.md`（分层计数、待仲裁清单、冲突摘要）+
   `result.json`（`case_id` + **全部** `output_contract` 字段 + `status` / `sources` /
   `uncertainty` / `change_records` / `artifacts` / `unresolved_contract_fields`）。
   无法填充的契约字段置 `null` 并列入 `unresolved_contract_fields`，**绝不编造**。

## 输出契约

| 产物 | 位置 | 内容 |
|---|---|---|
| `result.json` | `/app/output/` | `case_id` + 全部 `output_contract` 字段 + 诚实状态字段 |
| `merged_records.json` | `/app/work/` | 规范记录，含 `member_records`、`provenance`（字段级） |
| `dedup_decisions.jsonl` | `/app/work/` | 每候选对一行：`pair/tier/decision/reason_code/evidence` |
| `arbitration_queue.json` | `/app/work/` | 待仲裁 T3 对（未合并），含证据 |
| `conflict_log.json` | `/app/work/` | 跨来源字段冲突：`field/values/chosen/rule` |
| `identity_report.md` | `/app/work/` | 分层计数、待仲裁清单、冲突摘要 |

## 状态语义

- `status="ok"`（退出码 0）：全部分层判定闭合，无待仲裁、无隔离材料。
- `status="partial"`（退出码 2）：诚实降级——存在待仲裁 T3 对、材料被隔离、或未抽取到
  任何记录；`uncertainty` 中显式列明原因，**不静默**。
- `status="error"`（退出码 3）：输入无效（case.json 缺失/非法/无 `case_id`，
  裁决文件非法等）。
- 顶层异常一律捕获：写诚实 partial + 退出码 2，绝不崩溃裸栈。

## 规则边界和维护

- 跨标识符链接**只**认 reference_graph / import_state 的显式 `aliases` / `known_aliases`；
  严禁臆造 pmid↔doi。新增别名只能来自材料或显式裁决，不得来自模型先验。
- T3 阈值（Jaccard 0.6 / 姓氏重叠 0.5 / 年份差 1）与 reason_code 枚举维护于
  `references/matching-rules.md`；改阈值必须同步改该文件与示例。
- 来源优先级表维护于 `references/merge-policy.md` 的 `priority-json` 代码块，
  脚本启动时解析，可按字段覆盖；解析失败回退默认 publisher > crossref > europepmc。
- 本技能不做：引用网络扩展、查重之外的推荐、任何网络访问。

## 确定性与自查

- 材料扫描排序、记录 id 按扫描序赋号、候选对按 id 序遍历、规范记录按
  (DOI 否则标题) 排序、JSON 键排序输出——同一输入字节级可复现，幂等。
- 产物不含时间戳与随机量；`change_records` 只记录操作不含墙钟。
- 自查清单：`--help` 退出 0；重跑产物字节一致；每个候选对都有决策行；
  T3 对未合并且在仲裁队列；冲突日志与溯源字段齐全；契约字段无编造。

## 示例

`examples/synthetic-input/` 为**合成教学数据**（虚构论文、伪造 DOI `10.99966/...`、
`"Synthetic ..."` 标题），覆盖四类情形：DOI 精确重复（T1）、仅靠显式别名链接的
跨标识符重复（T1）、作者格式变体的书目重复（T2）、标题/年份微差必须待仲裁的近似
重复（T3，保持 pending）、以及一篇单源独立论文。`examples/synthetic-output/` 为脚本
**实际运行**产物；`adjudications.example.json` 演示裁决文件格式；
`run-record.md` 记录确切命令、为何 `status=partial` 是诚实结果、以及重跑与确定性说明。
