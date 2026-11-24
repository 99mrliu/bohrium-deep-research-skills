# 图表种类政策（figure-policy）

## 四分法与合法用途

| 种类 | 判定线索 | 合法用途 | 禁止用途 |
|---|---|---|---|
| data-figure（数据图） | caption 含 measured/data/curve/response 等；或页面含嵌入位图 | results 页证据、定量结论支撑 | 无（但引用须带 provenance） |
| schematic（示意图） | caption 含 schematic/diagram/illustration/overview/workflow | background/methods 页说明概念与流程 | **永远不得充当实验证据**；禁上 results 页 |
| table-image（表图） | caption 以 Table 开头 | 数值出处；重绘的数据来源之一 | 不得冒充趋势图 |
| others' result（他人结果） | caption 含 reproduced from / adapted from / 引文编号 | 仅在明确标注出处时用于 related work | 不得冒充本文结果 |

## 张冠李戴典型案例（必须避免）

1. 把方法示意图放到 results 页，配文 "our measurements show"——示意图不含任何
   测量数据，这是虚假证据。`fig_binding_lint.py` 的 `schematic-in-results` 规则
   直接拦截。
2. 把论文里他人综述中的对比图截来当自己工作的结果——provenance 无法标为
   original-crop（出处页码对不上）时应降级为 related-work 引用并写明出处。
3. 重绘图改了刻度或四舍五入数值却没改标注——`redraw_verify.py` 容差 0，直接
   error。
4. caption 缺失的图凭版式猜测种类——归入 unknown，必须 Agent 裁决并记入
   `change_records`，裁决前不得入 deck。

## 角色页与种类矩阵

| 页面角色 | 允许的种类 |
|---|---|
| title / agenda | 无图或 schematic-reference |
| background / related-work | schematic-reference、标注出处的他人结果 |
| methods | schematic-reference、original-crop（装置照片） |
| results | **仅** original-crop / redrawn-from-data 的 data-figure、table |
| discussion / limitations / conclusion | 可回引 results 已用图（同一 id） |
