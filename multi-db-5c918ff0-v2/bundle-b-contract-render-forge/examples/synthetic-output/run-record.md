# Run Record(运行记录)

**合成示例声明**:本目录输入为合成教学数据(`case.json` 中
`_note: "SYNTHETIC teaching data"`;虚构 DOI `10.99988/...`、虚构期刊、虚构
人名),仅用于演示渲染引擎行为,不代表任何真实文献。

## 生成命令(实际执行)

```bash
python3 scripts/render_forge.py \
  --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md \
  --work /tmp/rf-work-syn \
  --out examples/synthetic-output
```

退出码:`0`;`result.json` 中 `status: "success"`,全部 5 个契约字段
(`candidate_set` / `ranking_basis` / `evidence_records` /
`status_notes` / `coverage_statement`)均已语义填充,
`unresolved_contract_fields: []`,`render_gate_report.md` 五项门控全 PASS。

## 重跑与确定性验证

```bash
python3 scripts/render_forge.py --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md --work /tmp/rf-work-a --out /tmp/rf-out-a   # exit 0
python3 scripts/render_forge.py --case examples/synthetic-input/case.json \
  --task examples/synthetic-input/task.md --work /tmp/rf-work-b --out /tmp/rf-out-b   # exit 0
diff -r /tmp/rf-out-a /tmp/rf-out-b        # 无输出:两次产物字节级一致
diff -r /tmp/rf-out-a examples/synthetic-output   # 无输出:与本目录产物一致
```

确定性来源:目录扫描排序、JSON `sort_keys=True`、无时间戳/随机数、同分按
record_id 决胜;change_records 只记录参数为 default/custom 而不记录绝对路径。

## 合成数据与产物的对应关系(抽查)

- 材料 8 条原始记录(crossref 3、europepmc 3、publisher 2)去重合并为
  **4 条规范记录**:三库全中 1 条(rec-0001)、双库 DOI 命中 1 条
  (rec-0002)、单库 1 条(rec-0003)、无 DOI 靠标题+年份+第一作者命中 1 条
  (rec-0004,`match_basis: title+year+first_author`)。
- `coverage_matrix.md`:crossref `pmid=0`、europepmc `volume/issue/pages=0`,
  二者列入系统性缺失;rec-0003 列入单一来源记录。
- `provenance_chain.md`:rec-0001 记录 authors / journal 两个跨来源冲突,
  逐字段标注合并来源(publisher 优先)。
- `candidate_table.md`:rec-0001 score=18(4 个标题词命中 + 引用图入度 2)
  居首,与 `result.json.ranking_basis.ranking` 一致。

## 其他路径验证

- `--help` 退出码 0。
- case.json 缺失 → 退出码 3,`status: input_error`。
- `/app/work/merged_records.json` 预置时 → 消费上游产物
  (change_records 记录 `consumed_upstream_merged_records`),渲染不阻塞。
