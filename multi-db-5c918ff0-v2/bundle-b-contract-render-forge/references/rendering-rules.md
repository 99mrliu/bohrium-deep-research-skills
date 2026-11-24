# Rendering Rules(渲染规则)

所有产物为 UTF-8 Markdown / JSON;确定性、幂等、无墙钟。同一输入重跑,
产物字节级一致(`diff -r` 全等)。

## 1. 通用确定性规则

- 目录扫描:`os.walk` 的 `dirs.sort()` + 文件名字典序;所有集合输出前排序。
- JSON:`json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)` + 换行。
- 排序(score 相同)一律按 `record_id` 字典序决胜;record_id 为
  `rec-%04d`,按聚类出现顺序分配。
- 写文件先写 `.tmp` 再 `os.replace`(原子覆写,幂等)。
- 产物中禁止出现:时间戳、随机数、绝对输出路径(工件以相对 case 目录的
  路径 + out 目录 basename 记录)、环境相关字符串。

## 2. candidate_table.md

结构:`# Candidate Table` → 元信息(含机器可读标记
`<!-- canonical_records:N -->`)→ `## Scope notes`(task.md 中含
纳入/排除/范围/criterion 等提示的行,去重保序,≤8 条)→ `## Ranked
candidates` 表格:

```
| rank | record_id | DOI | PMID | year | title | matched query terms | score | source dbs |
```

- matched query terms = research_question + task.md 词项(小写,长度≥4,去
  停用词)在标题/上下文的命中集合。
- score = 3×标题命中数 + 1×上下文命中数 + 2×引用图入度(边语义
  citing→cited,对规范记录 DOI 计被引次数)。
- source dbs 徽标:`CR`=crossref,`EP`=europepmc,`PU`=publisher,
  `MR`=merged_records(上游);多库用 `+` 连接,按库名字典序。
- 空值渲染为 `—`;标题内 `|` 转义为 `\|`。

## 3. provenance_chain.md(溯源链记号)

每条规范记录一节,链式记号固定为:

```
## rec-000N — <doi 或 title>
- 来源库 → 材料 → 定位:        publisher → `materials/x.json` @ `records[i]`
- 去重判定: cluster_size=K; match_basis: doi, pmid, ... 或 (singleton)
- 合并取值: 表格 | field | merged value | source db | artifact | locator | state |
- 跨来源冲突: 字段名 + 变体数 + 裁决(优先级)+ 每个变体原文
- 成员缺失字段: 每成员在该记录中为空的字段列表
```

- `state ∈ {value, not_provided_by_any_source}`。
- 合并优先级:publisher(30) > crossref(20) > europepmc(10),
  **逐字段独立裁决**;上游 merged_records(5)兜底。
- 冲突定义:同一字段在不同来源成员间出现 >1 种规范化后不同的取值;作者与
  标题按规范化键(小写去标点 / 排序小写元组)判同。

## 4. coverage_matrix.md

- 计数矩阵(机器可读块 `<!-- matrix:begin -->` … `<!-- matrix:end -->`):

```
| field | <db1> | <db2> | <db3> | merged |
```

  单元格为**成员级**计数:该来源库的记录(member)中该字段非空的条数;
  `merged` 列为合并后规范记录非空条数。矩阵列按库名字典序。
- `## 单一来源记录`:`len(sources_seen)==1` 的规范记录表(record_id、doi、
  唯一来源),提示人工复核。
- `## 系统性缺失字段`:某库该字段 0 覆盖、但 merged 计数 >0,按库列出。
- `## Review appendix`:
  - `### Unresolved contract fields`:逐字段列原因;
  - `### Conflicts`:逐记录逐字段列冲突与裁决。

## 5. render_gate_report.md

`| # | check | result | detail |` 五门控表 + `gate_overall: PASS|FAIL`。
检查定义见 references/contract-playbook.md §4。报告自身也是工件,定稿后
重算 sha256 覆写进 result.json 的 artifacts。

## 6. result.json 结构(键序由 sort_keys 固定)

`case_id`, `status`, `generated_by`, `sources`[{path, sha256,
classified_as}], `uncertainty`[str], `change_records`[{seq, step, action,
detail}], `artifacts`[{path, location, sha256}], `unresolved_contract_fields`
[{field, reason}], 以及**按字典序混入的全部契约字段**。
