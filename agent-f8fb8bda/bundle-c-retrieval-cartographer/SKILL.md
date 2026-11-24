---
name: dr-retrieval-cartographer
description: 深度研究（deep research）文献综述 Skill，重心为检索规划与覆盖工程（retrieval planning & coverage engineering）：把研究问题拆解为可独立检索、带验收标准与依赖 DAG 的子问题，检索计划经机器门控校验（无环、无重复检索式、预算内、波次与依赖一致），覆盖矩阵（coverage matrix）与研究空白（research gaps）只从检索记录导出——搜过没有 ≠ 没搜过。触发词：深度研究、文献综述、检索规划、问题拆解、覆盖矩阵、研究空白、证据综合；deep research, literature review, retrieval planning, question decomposition, coverage, evidence synthesis, research gap。
---

# dr-retrieval-cartographer：检索规划与覆盖工程

## 定位

面向"深度研究 Agent：文献综述——综合证据，也说明边界"任务。本 Skill 把文献综述的
**检索规划（retrieval planning）**与**覆盖核算（coverage accounting）**两段机械化：
机械可判定的检查全部下沉到三个确定性 Python 脚本（仅标准库），Agent 只负责判断性工作
（补齐要素、撰写检索式与验收标准、判定相关性、综合结论）。

- `scripts/decompose.py`：六要素抽取 + SQ 骨架生成；
- `scripts/plan_check.py`：检索计划门控（P1–P5），exit 0 通过 / exit 1 违例 / exit 2 用法或 IO 错误；
- `scripts/coverage.py`：覆盖矩阵与研究空白导出，可选空白条目门控。

## 环境假设与预算纪律

- 输入：`/input/case.json`、`/input/task.md` 与材料文件；工作目录 `/app/work`；产物写入 `/app/output`。
- `case.json` 一律防御式解析；**`output_contract` 字段名因案例而异，凡涉及 result.json 的字段名必须动态读取，禁止硬编码**。
- 预算有限（模型请求 ≤64、900 秒）：脚本一次跑通即得结论，门控失败按 P 编号清单定点修复后重跑，不要盲目整体重来。

## 五阶段流程协议

### 阶段 0：契约初始化（contract init）

```bash
mkdir -p /app/work /app/output
python3 -c "import json; d=json.load(open('/input/case.json')); print(json.dumps({'case_id': d.get('case_id'), 'output_contract': d.get('output_contract')}, ensure_ascii=False, indent=2))"
```

记录 `case_id` 原样值与 `output_contract` 要求的全部字段名，后续 result.json 严格对齐。
`output_contract` 可能是对象（如含 `required_fields`）或列表，均需兼容。

### 阶段 1：问题拆解（decomposition）

```bash
python3 /skills/weekly-skill/scripts/decompose.py --task /input/task.md --case /input/case.json --output /app/output/decomposition.json
```

- 脚本抽取六要素（研究对象、机制/干预、对照、结局指标、时间范围、证据要求）并生成 4–6 个 SQ。
- **stdout 中 `[ACTION REQUIRED]` 列出的 TO_FILL 要素必须由 Agent 结合 case.json 与材料人工补齐**；
  同时补齐每个 SQ 的 `query_cn`/`query_en`/`acceptance_criteria` 占位。
- 验收标准写法、依赖标注规则见 `references/decomposition_schema.md`；
  仅当构造检索式确实需要另一 SQ 的结果时才标 `depends_on`。

### 阶段 2：检索执行（retrieval）

1. 按 `references/retrieval_policy.md` 撰写 `/app/work/retrieval_plan.json`
   （`waves[]` → `actions[]`；action 含 `action_id`、`sq_id` 或 `sq_ids`、`query`、`source_scope`、`stop_condition`、`wave`）。
2. 机器门控，**exit 非 0 不得执行检索**：

```bash
python3 /skills/weekly-skill/scripts/plan_check.py --plan /app/work/retrieval_plan.json --decomp /app/output/decomposition.json --max-actions 25
```

   P1 依赖无环 / P2 每 SQ 有 action 且三键非空 / P3 无归一化重复检索式（同一检索用 `sq_ids` 多标注）/
   P4 波次与依赖一致 / P5 预算内。违例按 P 编号定点修复后重跑本命令。
3. 门控通过后执行检索：W1 背景定界先行，W2 各 SQ 并行，W3 仅对 unmet 的 SQ 补检。
   每次检索向 `/app/work/search_log.jsonl` 追加一行：
   `{"action_id","sq_ids","query","source","hits":[{"dedup_key","title","relevant"}]}`；
   去重键 DOI 优先，否则首作者姓+年份+标题前 40 字符归一化（规范见 references）。

### 阶段 3：证据与综合（evidence & synthesis）

```bash
python3 /skills/weekly-skill/scripts/coverage.py --log /app/work/search_log.jsonl --decomp /app/output/decomposition.json --out-dir /app/output
```

- 产出 `/app/output/coverage_matrix.json`（每 SQ × source 相关命中；状态
  met ≥3 / unmet 1–2 / searched_absent 检索过但 0 相关 / not_searched 无记录；含饱和度信号）
  与 `/app/output/research_gaps.json`（高置信缺口仅来自 searched_absent；
  not_searched 一律 not_assessable；unmet 仅 low_coverage）。
- 综合结论时逐条证据回链到 `dedup_key` 与 `source`；冲突证据并列呈现并标注来源分歧。
- 若需在正文撰写研究空白条目，先写 `/app/work/gaps.md` 再过门控（exit 1 即存在凭空空白，必须删改）：

```bash
python3 /skills/weekly-skill/scripts/coverage.py --log /app/work/search_log.jsonl --decomp /app/output/decomposition.json --out-dir /app/output --gaps-file /app/work/gaps.md
```

### 阶段 4：交付门（delivery gate）

1. 组装 `/app/output/result.json`：`case_id` 原样写入；`output_contract` 要求的字段**按阶段 0 动态读到的字段名**逐一填充；
   诚实标注 `status`（complete/partial）、`sources`、`uncertainty`；partial 必须说明限度（哪些 SQ unmet/not_searched、哪些结论仅为推断）。
2. 交付校验：

```bash
python3 -c "import json; c=json.load(open('/input/case.json')); r=json.load(open('/app/output/result.json')); oc=c.get('output_contract') or {}; req=oc.get('required_fields', []) if isinstance(oc, dict) else (oc if isinstance(oc, list) else []); missing=[f for f in req if f not in r]; assert not missing, 'missing: %s' % missing; assert r.get('case_id')==c.get('case_id'), 'case_id mismatch'; print('result.json OK:', req)"
```

## 六要点 → result.json 区块映射

| 评分要点 | 来源产物 | result.json 落点 |
|---|---|---|
| 问题拆解 | decomposition.json | 六要素 + SQ 列表（含验收标准与依赖） |
| 检索覆盖 | coverage_matrix.json | 每 SQ 状态、by_source、饱和度信号 |
| 证据回链 | search_log.jsonl | 每条结论标注 dedup_key + source + action_id |
| 冲突证据 | 检索记录中的分歧命中 | conflicts 区块：并列双方及各自来源 |
| 综合结论 | Agent 综合 | 区分材料事实 / 合理推断 / 无法确定 |
| 研究空白 | research_gaps.json | 仅 searched_absent 可声称；not_searched 标 not_assessable |

上表"落点"为内容区块语义；具体字段名以 `output_contract` 为准，动态对齐。

## 可靠性与边界

- 三个脚本均为确定性实现：同一输入同一输出，产物 JSON 用 `ensure_ascii=False, indent=2`，不含随机数与时间戳。
- decompose 的启发式只负责起草骨架，抽不到即 TO_FILL 并显式提醒，绝不编造要素取值。
- 覆盖与空白结论只从 search_log.jsonl 导出：**搜过没有 ≠ 没搜过**。
- 完整可运行示例见 `examples/`（`bash examples/run_example.sh` 一键演示，含门控开火的埋雷变例）。
