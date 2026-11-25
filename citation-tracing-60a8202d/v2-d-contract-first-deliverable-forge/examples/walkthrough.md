# 合成示例端到端运行实录（SYNTHETIC / 非正式案例结果）

> 本示例全部文献为**虚构**（DOI 形如 `10.0000/synth.*`），**SYNTHETIC, not real
> papers**，仅用于演示与自查。`examples/run_out/` 下的产物是本 Skill 作者用
> 合成语料**真实运行**脚本得到的输出，不是手工编写的答案。

## 语料构成（examples/corpus/，4 个文件、5 条记录、4 种格式）

| 文件 | 格式 | 内容 |
|------|------|------|
| `crossref_seed.json` | Crossref 单条 `message` | 种子 `10.0000/synth.001`（2021），references 指向 synth.002、synth.003 与**未收录的** synth.999 |
| `crossref_batch.json` | Crossref `message.items` | `10.0000/synth.002`（2015，引用 synth.003）与 `10.0000/synth.003`（2012） |
| `europepmc.json` | EuropePMC `resultList.result` | 无 DOI 记录，标题与 synth.002 规范化后相同（演示标题键身份合并） |
| `citing.jsonl` | 通用 JSONL 节点 | `10.0000/synth.004`（2023，references 指向种子，演示反向索引恢复前向边） |

`case.json` 的 `output_contract` 除标准字段（case_id/seed_paper/candidates/edges/
evidence_records/status/uncertainty）外，另含两个**自定义字段** `layer_counts`
（object）与 `method_summary`（string），用于演示契约镜像对自定义字段的鲁棒填充。

## 实际运行命令与退出码（作者机器 macOS, Python 3.12）

```bash
cd <skill 根目录>
# 1) 契约骨架
python3 scripts/contract.py --skeleton --case examples/case.json --workdir examples/run_out/work
#    退出码 0 → examples/run_out/work/result_skeleton.json（9 个契约字段占位＋填充计划）
# 2) 管线（ingest 后先落 honest partial，再覆盖增强）
python3 scripts/pipeline.py --case examples/case.json --roots examples/corpus \
    --out examples/run_out/output --workdir examples/run_out/work
#    退出码 0；日志：parsed 5 records from 4 files (0 failed)；dedup 5 -> 4（1 merge）；
#    status=partial candidates=4 edges=10 stubs=1 merges=1
# 3) 人读交付包（bundle 内用 --svg-only 强制 SVG，避免二进制入库）
python3 scripts/render_pack.py --result examples/run_out/output/result.json --svg-only
#    退出码 0 → evidence_table.md / nodes.csv / edges.csv / preview_data.json / network_preview.svg
# 4) 契约门禁
python3 scripts/contract.py --verify --case examples/case.json --out examples/run_out/output
#    退出码 0，ok=true
```

## verify 逐字段表（真实输出摘要）

```
case_id: 'synth-case-001' (expected 'synth-case-001')  status: 'partial'
field              declared   state
case_id            string     filled
seed_paper         object     filled
candidates         array      filled
edges              array      filled
evidence_records   array      filled
status             string     filled
uncertainty        array      filled
layer_counts       object     filled   <- 自定义契约字段，已镜像填充
method_summary     string     filled   <- 自定义契约字段，已镜像填充
summary: fields=9 filled=9 empty=0 empty(excused)=0 missing=0
ok=true
```

## 预期输出要点（已在 run_out/output/result.json 中核对）

- 候选 4 条：`synth.002`、`synth.003`、`synth.004`（均 layer 1）＋ stub
  `10.0000/synth.999`（仅原始指针与 locator，未补造元数据）；
- 扩展边 10 条：4 条 reference 边（如实线）＋ 6 条由全语料反向索引恢复的 citation
  边（`direction_restored: true`）；每条边带 `{file, pointer}` locator；
- 身份合并 1 次：EuropePMC 记录按标题规范化键并入 `10.0000/synth.002`，
  明细见 `result.json.merge_log`（match_key=title）；
- `status=partial`：因存在 1 个 stub 诚实降级（非 ok）；uncertainty 两条
  （合并说明＋stub 说明）；
- `layer_counts={"layer_1": 4, "layer_2": 0}`、`method_summary` 为真实生成的中文摘要，
  两个自定义契约字段均被镜像填充并通过 verify；
- `network_preview.svg`：种子居中（红）、layer 1 蓝、stub 灰，reference 实线、
  恢复的 citation 边弯曲虚线；`preview_data.json` 为其坐标/边数据源。

## 关于 PNG 预览

matplotlib 可用时 `render_pack.py`（不加 `--svg-only`）会生成
`network_preview.png`。作者已真实验证该路径（输出到 `/tmp/ch60a8202d_v2d_pngtest/`
并目检：种子居中、节点按层着色、恢复的 citation 边弯曲虚线与 reference 实线可清晰
区分）。按平台约束二进制不入 bundle，故 bundle 内示例仅保留 SVG 预览；PNG 产物位于
`/tmp/ch60a8202d_v2d_pngtest/network_preview.png`，可用以下命令复现：

```bash
python3 scripts/render_pack.py --result examples/run_out/output/result.json \
    --out /tmp/ch60a8202d_v2d_pngtest
```

## 门禁负例（作者自测）

人为破坏一份 result.json（删 `edges`、清空 `method_summary`、篡改 `case_id`）后，
`contract.py --verify` 正确报出 `missing=1 / empty=1 / case_id 不一致`，
`ok=false`，退出码 1——门禁能有效拦截不完整交付。
