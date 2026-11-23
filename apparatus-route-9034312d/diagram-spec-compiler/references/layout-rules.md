# 版式规则 — compile_figure.py 的行为约定

本文档解释编译器的布局/布线/图例/确定性策略，便于 Agent 预测渲染结果并
向用户解释图面。所有规则均在纯 Python 标准库中实现，无外部依赖。

## 1. 分层（layering）

1. **回边检测**：先在全图上求强连通分量（Tarjan）；在每个非平凡 SCC 内从
   "SCC 入口节点"（有外部入边者，按最小外部入边 eid 再按 id 排序）做 DFS，
   指向灰色祖先的边记为回边；移除后迭代至无环。跨 SCC 的边永不误判，
   因此只有真正处于环上的边（循环物料、联锁反馈）成为回边。
2. **最长路径分层**：非回边构成 DAG，Kahn 拓扑序上
   `layer[v] = max(layer[pred]) + 1`。前向边必然严格向右（layer 递增）。
3. **层内排序**：初始按 id 排序，两轮重心（barycenter）下/上扫描减少交叉，
   同值按 id 兜底——全程确定性。
4. 节点按层成列，列内垂直堆叠并整体居中；roadmap 把"层"放进各 stage 泳道，
   泳道高度取该道内最高堆叠。

## 2. 端口式正交布线（Manhattan routing）

- 前向相邻边：源节点**右端口** → 列间隙中的垂直通道 → 目标**左端口**，
  路径为 `M→H→V→H` 三段。
- 同一间隙内多条边分配不同通道 x（中心 ±8px 递增），避免平行线重叠。
- 一个节点多条出/入边时，端口沿右/左边缘按目标/源 y 排序分布（12px 间距），
  减少交叉。
- 箭头用 SVG `<marker orient="auto-start-reverse">`，每种流型一个 marker，
  颜色取自样式表。

## 3. 回流与跨层边（底部绕行通道）

- 回边、以及跨越 ≥1 层的前向边，统一走**底部水平通道**（每条边独立 y，14px 间距）。
- 出/入节点均从**底端口**出发：先下 7px jog 到列间隙中的垂直通道再降到底部，
  避免穿越同列下方节点的包围盒；回边自右向左、跨层前向边自左向右。
- 回边强制虚线（样式表本有 dash 则沿用）+ 反向箭头 + `data-backflow="true"`，
  与正向边一眼可辨。

## 4. 图例按构造（legend by construction）

图例条目 = 实际使用的 flow_type（取样自 `styles.flow_types` 同一样式对象画线样）
+ 实际使用的节点 kind（画迷你形状）+ 存在回边时的"回流边"条目。
**图例与图形共享同一数据源**，因此二者不可能不一致；未使用的样式不进图例。
图例自动换行排版，宽度跟随内容。

## 5. 节点形状

| kind | 形状 | 备注 |
|---|---|---|
| unit | 圆角矩形 rx=8 | `parts` 逐行子隔室（分隔线+小字） |
| step | 矩形 rx=4 + 左上编号徽章 | 徽章填 `num`，文字右移避让 |
| stage | chevron 箭头形 | 用于 roadmap 里程碑 |
| data | 平行四边形（斜边 12px） | 储罐/数据/记录 |
| note | 虚线边框注释框 | 浅黄底 |

节点尺寸由文本估算（CJK 全宽、ASCII 0.56 宽）+ 内边距自动得出，spec 不写坐标。

## 6. 画布策略

- `canvas:"auto"`：内容包围盒 + 边距 → 输出毫米尺寸，记入 render_log。
- 固定画布：内容超出时整体等比 `scale()` 缩小（含泳道/图例，标题不缩放），
  `render_log.scale < 1` 并产生 warning；scale ≥ 0.6 通常仍可读，否则建议 auto。

## 7. 字体策略

- 探测：`fc-list :lang=zh family`（若存在）+ 常见路径
  （macOS PingFang/Hiragino/STHeiti；Linux Noto Sans CJK、文泉驿）。
- SVG 根节点写完整 fallback 链：探测到的优先，其余知名 CJK 字体殿后，
  最后 `sans-serif`；链与探测结果记入 render_log.font_chain / fonts_detected。
- **未探测到 CJK 字体只告警不失败**（tofu 风险写入 warnings）：SVG 是矢量源文件，
  到读者机器上仍可能正常渲染。

## 8. 可编辑 SVG 结构

```
<svg>                       font-family 回退链在根上
 ├─ <defs>                  每种流型一个箭头 marker
 ├─ <g id="layer-title">    标题（真实 <text>，非路径）
 ├─ <g id="layer-content">  溢出缩放 transform 挂在这里
 │   ├─ <g id="layer-stages">   泳道（仅 roadmap）
 │   ├─ <g id="layer-edges">    <g id="edge-eXX" data-eid data-from data-to data-flow data-backflow>
 │   ├─ <g id="layer-nodes">    <g id="node-<id>" data-eid data-kind transform="translate(x,y)">
 │   └─ <g id="layer-legend">   图例
```

全部文字为真实 `<text>`；每个元素独立分组带 `data-eid`，可在 Inkscape/Illustrator/
浏览器 DevTools 中直接选中编辑。

## 9. 确定性（字节级）

- 所有迭代排序（id、eid、层号、端口序、通道序）；无随机数、无时间戳、无环境依赖输出。
- 所有坐标 `round(x, 2)` 定圆并消除 -0.00。
- 验证：`compile_figure.py` 两次运行 + `diff`（应为空）；`--check-determinism`
  做同进程双渲染比对并写入 render_log.determinism；render_log 同时记录
  spec 与 SVG 的 SHA-256，便于溯源。
- 这支撑**保源编辑**：编辑类任务只改 spec（JSON diff 即 change_records），
  重渲染得到确定的新 SVG。
