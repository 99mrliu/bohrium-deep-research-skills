# artifact-guide.md — 交付物结构与确定性布局算法

本文件说明 `scripts/render.py` 产出的每个交付物的结构、审查方式，以及**确定性分层
布局算法**的全部细节（纯 Python 标准库，无 graphviz、无网络、无第三方包）。

## 1. 确定性分层布局算法（graph.svg / query_<id>.svg）

1. **列 = 实体类型**：每个出现过的实体类型占一列，列顺序固定为
   `researcher → task → dataset → claim → sample → method → material → metric → condition → note`
   （不在表中的类型按字典序追加在末尾）。该顺序一旦定义即固定，同时让绝大多数关系方向
   （claim→sample、claim→metric、claim→condition、sample→material、method→metric）指向
   右方，减少反向边。
2. **列内排序**：节点按 `(label.casefold(), id)` 排序，自上而下顶对齐堆叠。
3. **节点盒**：标签按 ≤26 字符贪心折行、最多 2 行（超出以 … 截断，完整标签在 `<title>`
   悬停提示中）；盒宽由最长行字符数决定（96–232px），盒高随行数。颜色按类型取固定色板。
4. **边路由**：三次贝塞尔曲线，端点为"源盒中心 → 目标盒中心"连线与盒边界的交点；
   控制点沿水平方向伸出（跨列边）；**同列边**向右弓出 90px；箭头标记指向 target；
   关系标签放在贝塞尔中点（t=0.5 的精确中点公式）的白色小签上。
5. **画布**：宽 = 列数 × 270 + 边距；高 = 最高列高 + 边距；坐标保留 1 位小数。
6. **查询高亮**：`query_<id>.svg` 与 `graph.svg` 使用**完全相同的布局**（同一坐标系），
   仅把结果子图的节点/边加粗为红色（`#d62728`），其余整体降至 12% 透明度——因此评审者
   可以逐坐标对照全图与子图。
7. **确定性**：同样的 graph.json 永远产生字节一致的 SVG（排序固定、无随机数、无墙钟
   时间戳）。

## 2. 交付物逐个说明

### result.json
镜像 `case.json.output_contract` 的每一个键；额外含 `status`（success/partial/unable）、
`sources`、`uncertainty`、`change_records`、`artifacts`、`contract_notes`。默认不含任何
墙钟时间；只有显式 `--run-meta` 才加 `run_meta` 块（且时间只出现在该块内）。

### report.html（签名产物）
自包含单文件，无外部依赖，浏览器直接打开：
1. 全图内联 SVG；2. 每个查询：内联高亮 SVG + 参数 + 路径列表 + 冲突检查表 + 结果边表 +
   未确定/未知项列表；3. 证据索引表（EV 编号、来源、段落、小节、逐字引文、子串校验标记）；
4. 合并账本 / 非合并登记 / 保留的数值冲突 / 未报告列表；5. 机械校验统计。
SYNTHETIC 示例输出带醒目的黄色合成声明条。

### graph.svg / query_<id>.svg（签名产物）
见 §1。审查要点：列标题是否按类型分组；标签是否可读（截断处悬停看全名）；红色高亮
是否正好覆盖查询结果子图；边标签与 CSV 中的 relation 是否一致。

### nodes.csv / edges.csv
UTF-8、首行表头、按 id 排序。`evidence_refs` 列为 `S1:s1p07` 形式的地址列表，
可与 evidence_index.json 对照。

### graph.jsonld
JSON-LD 1.1，`@graph` 中节点为 `node/<id>`、边为 `edge/<id>`，证据内联。词汇表 URI
为示例命名空间（SYNTHETIC 演示用）。

### graph.graphml
标准 GraphML，`type`/`label`/`relation`/`qualifiers`/`evidence` 以 `<data>` 键承载，
可直接导入 Gephi/Cytoscape。

### evidence_index.json
每个 (条目, 证据) 对一行：`evidence_id`（EV001…，节点在前边在后、按 id 排序）、
`item_kind`/`item_id`、`source_id`/`paragraph_id`/`section`、`quote`、
`quote_verified`（渲染时对语料**重新**做的精确子串校验结果）。

### verification_report.json
verify 阶段的统计（总行数/接受/拒绝/按操作/按原因码）与全部被拒绝行（含原因码与原行
截断），用于展示"抽得准"的机械门槛确实生效。

## 3. 审查清单（评审者 5 分钟走查）

1. 打开 `report.html`：黄色 SYNTHETIC 声明（示例时）、全图可读、每个查询有高亮图与结果表。
2. 在证据索引随机抽 3 条引文，到 `primary/secondary-material.json` 里核对是否逐字出现
   （也可看 `quote_verified` 列）。
3. 对照 §4：合并有理由与归一化键；"TiO2" 类同名不同物在非合并登记中；数值冲突（如
   21.1% vs 18.7%）是两条独立 claim 且条件不同、resolution=preserved。
4. `report.md`、`nodes.csv`、`graph.graphml` 的节点/边计数一致。
5. 重跑 `python3 scripts/run_minimal_example.py`，输出应与已提交版本字节一致（确定性）。
