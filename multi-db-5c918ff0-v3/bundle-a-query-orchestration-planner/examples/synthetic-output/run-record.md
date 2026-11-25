# 运行记录(合成示例)

> **本目录全部数据为合成产物**:所有文献、DOI(`10.99977/...`)、作者、期刊、
> 摘要、引用图均为虚构,仅演示接口与流程,非正式案例结果。
> 本目录的 `result.json` / `query_plan.json` / `coverage_declaration.json` /
> `query_ledger.jsonl` 由以下命令**真实执行**生成(非手工编写)。

## 环境与命令

- 引擎:`scripts/query_planner.py`(Python 3 标准库,离线)
- 执行时的工作目录:`/tmp`(演示"任意 cwd 均可运行")
- facets 来源:`examples/synthetic-input/facets.json`(模型步骤产物,示例中手工编写)

```bash
B=/path/to/bundle-a-query-orchestration-planner
cd /tmp
python3 "$B/scripts/query_planner.py" run-all \
  --input  "$B/examples/synthetic-input" \
  --work   /tmp/qo-wf \
  --output /tmp/qo-of \
  --facets "$B/examples/synthetic-input/facets.json"
echo "exit=$?"
```

随后将 `/tmp/qo-of/` 的四份交付物复制入本目录。

## 实测退出码与日志

```
[parse] case_id=synthetic-query-orch-001 files=4 missing=0 quarantined=0 truncated=1
[plan] source_dbs=crossref,europepmc,publisher plans=3
[reconcile] present=2 gaps=1 truncations=1 ledger_lines=3
[finalize] status=partial unresolved=1 gaps=1
[selfcheck] PASS: 18 pass, 0 fail
[run-all] 完成: {"parse": 0, "plan": 0, "reconcile": 0, "finalize": 0, "selfcheck": 0}
exit=0
```

## 关键观察

1. **publisher 缺口已显式声明**:`coverage_declaration.json.gaps[0]`
   (`db=publisher`,`impact.facets_losing_coverage=["F2"]`),
   且 `result.json.uncertainty` 含 `kind=absent_db` 条目;status=partial。
2. **Crossref 截断被标记**:`total-results=57 > items=3` →
   `truncation_flags` 与 `open_questions`(提示补采分页)。
3. **查询回响核对通过**:crossref 与 europepmc 均 `query_echo=matched`
   (重合度 1.0);publisher 无响应故 `not_echoed`。
4. **下游边界守信**:契约字段 `evidence_records` 为 `null` 并登记于
   `unresolved`(原因:证据抽取属下游职责);其余 4 个契约字段均已确定性填充。
5. **候选集未去重**:`candidate_set` 含 5 条登记,其中 DOI
   `10.99977/zk7.0002` 在 crossref 与 europepmc 各出现一次——刻意保留,
   去重是下游技能的事。

## 验证过的异常路径(实测退出码)

| 场景 | 命令形态 | 退出码 | 表现 |
|---|---|---|---|
| `--help` | `query_planner.py --help` | 0 | 打印全部子命令帮助 |
| 完整 run-all | 上述命令 | 0 | status=partial(缺口已声明),selfcheck PASS |
| 确定性重跑 | 同命令、两个全新 work/output 目录 | 0 / 0 | `diff -r` 字节一致 |
| case.json 缺失 | `--input` 指向空目录 | 3 | 仍写出最小 result.json(status=failed) |
| plan 无 facets | parse 后直接 `plan`(无 facets.json) | 2 | 明确提示由模型补齐 facets 后重跑 |
| run-all 无 facets | 省略 `--facets` 且 work 中无 facets.json | 1 | plan=2 降级,reconcile 跳过,selfcheck FAIL(产物缺失如实上报) |

## 复现字节一致性

```bash
python3 "$B/scripts/query_planner.py" run-all --input "$B/examples/synthetic-input" \
  --work /tmp/w1 --output /tmp/o1 --facets "$B/examples/synthetic-input/facets.json"
python3 "$B/scripts/query_planner.py" run-all --input "$B/examples/synthetic-input" \
  --work /tmp/w2 --output /tmp/o2 --facets "$B/examples/synthetic-input/facets.json"
diff -r /tmp/o1 /tmp/o2   # 无输出 = 字节一致
```
