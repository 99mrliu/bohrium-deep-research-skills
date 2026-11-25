# contract-first-deliverable-forge

> challenge-60a8202d「引文追踪与关联文献发现」参赛 Skill（v2 五件套之 d 件）。
> 工程重心：**契约优先的下游交付与渲染工程**——`output_contract` 机器校验、
> 人读证据包、引用网络图预览。

## 这是什么

一个可被 Agent 一条命令调用的确定性 Python 管线：

1. 从 `case.json` 的 `output_contract` 生成 `result.json` 骨架（逐字段占位＋填充计划）；
2. 递归发现并按格式解析本地语料（Crossref / EuropePMC / OpenAlex / 通用 JSON /
   JSONL / CSV / TSV / edgelist / bib），DOI＋标题双键去重，做 1–2 层前后向引用扩展
   （前向边由全语料反向索引恢复并标注 `direction_restored`），然后**按
   `output_contract` 逐字段镜像填充** `result.json`（含自定义契约字段）；
3. 渲染人读交付包：证据表 Markdown、节点/边 CSV、以种子为中心的引用网络预览图
   （matplotlib 可用出 PNG，缺失时标准库手写 SVG），预览同时保留 `preview_data.json`
   数据源供复核；
4. 交付门禁 `contract.py --verify` 机器校验：case_id 一致、契约字段在场且非占位、
   `status` 合法，打印逐字段填充状态表并以退出码给出结论。

诚实性设计：ingest 完成即落盘 honest partial `result.json`；解析不出的引用目标保留
为 stub（绝不补造元数据）；无结果/冲突/解析失败写入 `status`/`uncertainty`。
默认零网络，仅 Python 3 标准库（matplotlib 为 guarded import，缺失自动降级 SVG）。

## 怎么跑

```bash
# Harbor 契约（默认值即适配）
python3 scripts/pipeline.py --case /input/case.json --out /app/output --workdir /app/work
python3 scripts/render_pack.py --result /app/output/result.json
python3 scripts/contract.py --verify --case /input/case.json --out /app/output

# 本地合成示例（详见 examples/walkthrough.md）
python3 scripts/contract.py --skeleton --case examples/case.json --workdir examples/run_out/work
python3 scripts/pipeline.py --case examples/case.json --roots examples/corpus \
    --out examples/run_out/output --workdir examples/run_out/work
python3 scripts/render_pack.py --result examples/run_out/output/result.json --svg-only
python3 scripts/contract.py --verify --case examples/case.json --out examples/run_out/output
```

## 目录结构

```
├── SKILL.md                     # Agent 使用说明（运行契约、异常表、自查方法）
├── README.md                    # 本文件
├── GITHUB_URL.txt               # 仓库链接
├── scripts/
│   ├── contract.py              # --skeleton 生成契约骨架 / --verify 逐字段机器校验
│   ├── pipeline.py              # 语料发现→解析→去重→引用扩展→契约填充 result.json
│   └── render_pack.py           # 人读交付包渲染（证据表/CSV/网络预览 PNG 或 SVG）
├── references/
│   ├── contract_fields.md       # output_contract 镜像规则与字段语义
│   └── deliverable_layout.md    # /app/output 交付物布局与人读包说明
└── examples/                    # 合成最小示例（SYNTHETIC, not real papers）
    ├── case.json                # 含自定义字段的 output_contract
    ├── task.md
    ├── corpus/                  # 5 篇虚构文献记录（4 个文件、4 种格式）
    ├── walkthrough.md           # 端到端运行实录
    └── run_out/                 # 合成示例的真实运行产物（非正式案例结果）
```

## 合成示例声明

`examples/` 下全部文献为**虚构**（DOI 形如 `10.0000/synth.*`），仅用于演示与自查，
**SYNTHETIC / not real papers / 非正式案例结果**，不构成任何真实科研结论。
