---
name: contract-render-forge
description: 下游契约与渲染引擎(多数据库联合检索 Bohrium Playground 挑战的 OUTPUT 侧技能)。解析 case.json output_contract 的三种形态(dict/list/换行字符串)并挖掘 task.md 显式交付字段,绝不新增或丢弃契约字段;嗅探-分类 crossref/europepmc/publisher JSON、reference_graph、import_state 材料,归一化、三路去重(DOI 精确/PMID 精确/标题+年份+第一作者姓)、按 publisher>crossref>europepmc 逐字段合并并记录字段级溯源;确定性渲染 candidate_table.md、provenance_chain.md、coverage_matrix.md(含未决字段与冲突的 review appendix);门控装配 result.json——全部契约字段语义填充,填不出一律 null + unresolved_contract_fields,绝不编造,附带 case_id/status/sources(sha256)/uncertainty/change_records/artifacts,且所有渲染声明(记录数、覆盖计数)由门控从数据重算而非硬编码。Python 3 标准库、离线、无随机数、产物无墙钟、幂等。
---

# contract-render-forge:下游契约与渲染引擎

检索工作的价值只在其交付物对声明的 `output_contract` 完整、每条结论可追溯、
人可复核时才成立。本技能拥有 OUTPUT 侧:契约发现 → 证据摄入 → 确定性渲染 →
契约门控装配。渲染与可验证性是重心,记录匹配只求"小而真"。

## 何时使用

- 运行环境提供 `/input/case.json` + `/input/task.md` + 离线材料文件(Crossref /
  EuropePMC / 出版商 API 响应 JSON、reference graph、organizer 增量导入状态),
  要求向 `/app/output/result.json` 交付 `output_contract` 声明的全部字段。
- 需要候选排序表、逐记录溯源链、数据库×字段覆盖矩阵等可复核工件,且任何字段
  无法由材料支撑时必须显式置 null 而不是编造。
- 上游 agent 可能已经写出 `/app/work/merged_records.json` —— 本技能自动检测并
  直接消费(记入 change_records),渲染永不阻塞。

## 固定运行方式

安装位置:`/skills/weekly-skill`。标准调用(平台默认路径):

```bash
python3 /skills/weekly-skill/scripts/render_forge.py \
  --case /input/case.json --task /input/task.md \
  --work /app/work --out /app/output
```

参数均有默认值(`--case /input/case.json`、`--task /input/task.md`、
`--work /app/work`、`--out /app/output`),`--help` 退出码 0。若安装路径未知,
回退定位:

```bash
find / -maxdepth 6 -name "render_forge.py" 2>/dev/null
```

脚本仅依赖 Python 3 标准库;禁止联网、禁止随机数、产物中不出现墙钟时间。

## 完整工作流

1. **STEP 0(脚本自动,先于一切输入)**:写出诚实早期骨架
   `result.json`(`status="partial"`,无任何推断值)。任何后续失败都以此为基础
   降级,绝不留下空文件。
2. **契约发现(脚本)**:解析 `output_contract` 三种形态——dict 形
   (field→spec)、list 形(字段名列表)、字符串形(换行分隔);挖掘 task.md
   中反引号字段名与"输出字段/deliverable"行作佐证(绝不据此新增契约字段);
   写 `/app/work/contract_fields.json`(有序字段列表 + spec 来源)。
3. **证据摄入(脚本)**:发现材料(case.json `materials` 声明 + case 目录下全部
   `*.json`,排序去重);嗅探分类(crossref 形 `status=ok+message.items`、
   europepmc 形 `hitCount+resultList.result`、publisher 形、reference_graph、
   import_state);归一化为通用记录(区分 value / not_provided);按
   (a) 归一化 DOI 精确、(b) PMID 精确、(c) 归一化标题+年份+第一作者姓 聚类去重;
   按 publisher>crossref>europepmc **逐字段**合并,记录字段级 provenance
   (来源库、工件、JSON 定位符、状态);检测跨来源同字段冲突并记录裁决方式。
   若 `/app/work/merged_records.json` 已存在则直接消费。
4. **确定性渲染(脚本)**:写三个 Markdown 工件——
   `candidate_table.md`(按 research_question/task.md 词项评分排序:标题命中×3
   +上下文命中×1+引用图入度×2,同分按 record_id;含 scope notes 与来源徽标
   CR/EP/PU/MR);`provenance_chain.md`(逐记录:来源库→材料→原始定位→字段
   映射→去重判定→合并取值,每字段带来源标注、冲突变体、成员缺失字段);
   `coverage_matrix.md`(库×关键字段成员级计数矩阵、`merged` 列、单一来源
   记录表、系统性缺失字段标记,以及 review appendix:未决契约字段 + 冲突清单)。
5. **契约门控与装配(脚本)**:装配 `result.json`:全部契约字段按字段名语义
   填充(candidate/rank/evidence/coverage/status|note/graph|reference/import);
   无语义填充器或撞上保留键 → 该字段为 null 并写入 `unresolved_contract_fields`
   与 `uncertainty`。门控检查:契约键齐全;各工件 sha256 匹配;候选数与覆盖
   矩阵计数**从数据重算**并与渲染文本比对;null 字段与 unresolved 清单一致。
6. **模型判断步骤(留给 agent,不在脚本内)**:排序结果的业务解读、候选纳入/
   排除的最终学术判断、对 single-source-only 记录的人工复核结论,应写入交付
   说明或附加笔记;脚本只保证上述机械步骤确定、可追溯。
7. **预算意识**:平台限额 64 次请求 / 900 秒。本技能全程离线脚本化,LLM 只需
   触发命令并阅读 `render_gate_report.md` 与 `coverage_matrix.md` 的 review
   appendix 即可定位问题,把请求预算留给真正的学术判断。

## 输出契约

`/app/output/` 下:

- `result.json` —— 必含 `case_id`、`status`(`success|partial|input_error`)、
  `sources`(路径+sha256+分类)、`uncertainty`、`change_records`、`artifacts`
  (路径+sha256),以及 `output_contract` 声明的**每一个**字段;填不出的字段为
  `null` 且同步列入 `unresolved_contract_fields`。**绝不编造任何值。**
- `candidate_table.md`、`provenance_chain.md`、`coverage_matrix.md`、
  `render_gate_report.md`(门控检查结果,`gate_overall: PASS|FAIL`)。

`/app/work/` 下:`contract_fields.json`(契约发现结果)、`merged_records.json`
(合并后的规范记录,幂等重跑时作为上游产物被检测并消费)。

## 状态语义

- `success`(退出码 0):全部门控检查通过、无未决契约字段、至少一条规范记录。
- `partial`(退出码 2):诚实降级——存在未决字段、无记录可提取、或任何非致命
  异常(顶层 try/except 兜底,脚本永不崩溃)。骨架阶段即为此态。
- `input_error`(退出码 3):case.json 缺失、非法 JSON、非对象或缺 `case_id`。

## 规则边界和维护

- 不新增、不丢弃、不改写 `output_contract` 字段;task.md 挖掘结果只作佐证。
- 无证据 → null + `unresolved_contract_fields` + `uncertainty`;禁止以常识
  补全题录字段,禁止注入材料中不存在的记录。
- 契约字段名与保留键(`status`、`sources` 等)冲突时,保留键优先,该契约字段
  记为 unresolved 并说明原因。
- `artifacts` 列出全部输出工件(含 `result.json` 之外的四个 Markdown;
  `result.json` 自身为清单载体,不自我哈希)。`render_gate_report.md` 的哈希
  在其定稿后重算覆写,保证清单与磁盘一致。
- 上游 `merged_records.json` 消费与否均记入 `change_records`;内置管线保持
  紧凑——本技能重心是渲染与可验证性,而非匹配技巧。
- 维护:新增契约字段语义填充器时,只读 `ctx` 中已有数据;所有新计数必须能被
  门控重算。

## 确定性与自查

- 确定性:目录扫描排序、JSON `sort_keys=True` 输出、无时间戳/随机数;同一输入
  重跑产物字节级一致(示例目录附双跑 diff 记录)。
- 幂等:先写 `.tmp` 再 `os.replace`;重跑覆盖同名工件。
- 自查顺序:`--help` → 跑合成例(退出码 0、`status=success`)→ 重跑至临时目录
  `diff -r` 全等 → 核对 `render_gate_report.md` 全部 PASS → 核对
  `coverage_matrix.md` 的 review appendix 无未决字段。

## 示例

`examples/synthetic-input/` 与 `examples/synthetic-output/` 为**合成教学数据**
(声明:`_note: "SYNTHETIC teaching data"`;虚构 DOI `10.99988/...`、虚构期刊
与人名),含 crossref/europepmc/publisher 三库响应、保留引用图与增量导入状态,
4 条互相重叠的虚构论文(三库全中 / 双库 DOI 命中 / 单库 / 无 DOI 靠
标题+年份+作者去重),输出由真实运行脚本生成,`run-record.md` 记录命令与
确定性验证。
