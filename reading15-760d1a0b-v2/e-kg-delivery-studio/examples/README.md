# examples/ — SYNTHETIC 合成示例（非真实论文）

本示例的全部内容（两篇小论文、DOI、作者、数值、结论、抽取结果、输出产物）都是
**为演示而合成的（SYNTHETIC example, not real papers）**。`synthetic/output/` 下
提交的文件是演示产物，**不是正式案例答案**。

## 目录结构

```
examples/
└── synthetic/
    ├── input/                    # 模拟 /input（符合运行时契约的 6 个文件）
    │   ├── case.json             #   output_contract + 3 个 query_specs
    │   ├── task.md               #   任务简报
    │   ├── material.json         #   段落聚合索引（{"materials": [...]} 形态）
    │   ├── primary-material.json #   S1 全文（12 段）
    │   ├── secondary-material.json # S2 全文（11 段）
    │   └── corpus-manifest.json  #   角色/doi/sha256 归属清单
    ├── work/
    │   └── extractions.jsonl     # 模拟"模型写的唯一工件"（手工编写的演示数据；
    │                             #   含 1 行故意格式错误、1 行故意地址错误，
    │                             #   用于演示容错解析与机械拒绝）
    └── output/                   # 模拟 /app/output：已提交的生成产物（13 个文件）
```

## 示例覆盖的测试装置（对应 SPEC §4）

1. **跨篇别名对**：S1 "methylammonium lead iodide (MAPbI3)" ↔ S2 "MAPbI3"
   → `merge` N01←N02，键 `mapbi3`（进 merge ledger）。
2. **首提缩写**：S1 "power conversion efficiency (PCE)"（另有 Voc/Jsc/FF）。
3. **跨篇数值冲突（不同条件）**：S1 冠军 PCE 21.1%（1-sun 初始）vs S2 18.7%
   （85 °C/85% RH 湿热 500 h 后）→ 两个独立 claim 节点，`resolution="preserved"`。
4. **同名不同物陷阱**：两篇都有 "TiO2"，S1 是致密电子传输层、S2 是介孔支架
   → 显式 `nonmerge`（N03≠N04，键 `tio2`）。
5. **未报告项**：hysteresis index 两篇均未报告（S1 明说未测）→ unreported 列表，
   自动进入每个查询的 undetermined。
6. **3 个 query_specs**：q1 MAPbI3 的 1 跳邻域；q2 全部 `measures` 边；
   q3 champion 器件 → 老化器件的路径 + 数值冲突检查。

## 运行

```bash
python3 scripts/run_minimal_example.py        # 在本 bundle 根目录下
```

预期控制台输出（路径随环境不同；退出码 0）：

```
discover: 2 source(s), 23 paragraph(s), 0 warning(s)
verify: 58/67 line(s) accepted, 2 rejected (ADDRESS_NOT_FOUND=1, MALFORMED_JSON=1)
build: 25 node(s), 27 edge(s), 1 merge(s), 1 non-merge(s), 1 preserved conflict(s)
query: 3 executed (3 ok, 0 empty, 0 failed)
render: 12 artifact(s) written to .../examples/synthetic/output
assemble: result.json status=success, contract keys=7, null keys=none
$ .../python3 .../scripts/kg_pipeline.py all --input .../input --work /tmp/... --extractions .../extractions.jsonl --output .../output

--- outputs in .../examples/synthetic/output ---
  edges.csv                        2644 bytes
  evidence_index.json             16862 bytes
  graph.graphml                    9576 bytes
  graph.jsonld                    21748 bytes
  graph.svg                       20163 bytes
  nodes.csv                        1862 bytes
  query_q1.svg                    20869 bytes
  query_q2.svg                    20832 bytes
  query_q3.svg                    <略>
  report.html                     <略>
  report.md                        <略>
  result.json                      <略>
  verification_report.json          983 bytes
example run OK (SYNTHETIC demo outputs, NOT formal case answers)
```

（文件字节数以当前提交为准；重跑应得到字节一致的输出——确定性。）

## 输出文件清单（13 个）

`result.json`（镜像 output_contract，status=success）、`graph.svg`（全图）、
`query_q1.svg`/`query_q2.svg`/`query_q3.svg`（查询高亮子图）、`report.html`（自包含
报告）、`report.md`、`nodes.csv`、`edges.csv`、`graph.jsonld`、`graph.graphml`、
`evidence_index.json`（53 条证据全部 `quote_verified=true`）、
`verification_report.json`（2 行被拒绝：1 行格式错误、1 行地址不存在）。

审查方式见 `references/artifact-guide.md` 的"5 分钟走查"。
