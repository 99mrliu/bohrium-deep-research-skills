# /app/output 交付物布局与人读包说明

`contract-first-deliverable-forge` 的交付分两层：机器可读主结果 + 人读证据包。
所有预览产物同时保留数据源（JSON/CSV），保证任何图、表都可回到结构化数据复核。

## 一、目录布局

```
/app/output/
├── result.json            # 机器可读主结果（契约镜像填充，见 contract_fields.md）
├── evidence_table.md      # 人读证据表（render_pack.py 生成）
├── nodes.csv              # 节点表：id,doi,title,year,layer,stub
├── edges.csv              # 边表：source,target,kind,direction_restored,locator_file,locator_pointer
├── preview_data.json      # 预览图数据源：放射布局坐标 + 边列表
├── network_preview.png    # 引用网络预览（matplotlib 可用时）
└── network_preview.svg    # 引用网络预览（matplotlib 缺失或 --svg-only 时，标准库手写）
/app/work/
└── result_skeleton.json   # 契约骨架 + 逐字段填充计划（contract.py --skeleton）
```

PNG 与 SVG 只会出现其一：matplotlib 为 guarded import，缺失时降级 SVG；
无二进制交付场景用 `--svg-only` 强制 SVG。

## 二、evidence_table.md

三段结构：

1. **头部**：case_id、status、种子（标题/DOI/id）、候选与边计数；
2. **候选表**：逐候选 `标题 | 年份 | 层 | stub | 关联依据 | locator`，
   关联依据说明该候选经哪条边被发现（后向 reference / 前向 citation 恢复）；
3. **引用边表**：逐边 `source | target | kind | direction_restored | locator`；
4. **uncertainty 附录**：原样列出 result.json 的不确定性条目。

表中 locator 统一渲染为 `文件名 :: pointer`，pointer 为 JSON 路径
（如 `$.message.items[0]`）或行号（如 `line 1`、`row 3`），可直接回原始语料核对。

## 三、CSV 表

- `nodes.csv`：种子 `layer=0`，候选 `layer>=1`，stub 行 `stub=true`；
  行数 = 候选数 + 1（种子在语料中解析成功时）。
- `edges.csv`：与 `result.json.edges` 一一对应，`direction_restored` 以
  `true/false` 文本给出，locator 拆成两列方便表格软件筛选。

## 四、网络预览图

- 布局：以种子为中心的放射布局，layer 1 内圈、layer 2 外圈，同层均匀分布；
  确定性排序（按层、按 id），重复运行图不变。
- 着色：种子红 `#c0392b`、layer 1 蓝 `#1f77b4`、layer 2 绿 `#2ca02c`、
  stub 灰 `#8c8c8c`。
- 边：reference（citing→cited）实线；由反向索引恢复的 citation（cited→citing）
  弯曲虚线，避免与反向 reference 边重叠导致方向语义不可读。
- 复核：`preview_data.json` 含每个节点的 `{id,title,layer,stub,x,y}` 与每条边的
  `{source,target,kind,direction_restored}`，是图的唯一数据源，可据此重绘或审计。

## 五、交付自查门禁（顺序）

1. `pipeline.py` 退出码 0（status ok/partial）；
2. `render_pack.py` 退出码 0 且五件产物齐备（PNG/SVG 计一件）；
3. `contract.py --verify` 打印逐字段表全 `filled`（或有豁免）、`ok=true`、退出码 0；
4. 抽查：候选数一致（result.json == evidence_table == nodes.csv − 1），
   抽 2 条边回 locator 核对。
