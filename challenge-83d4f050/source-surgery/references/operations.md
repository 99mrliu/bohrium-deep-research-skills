# SVG DOM operation reference

## Common envelope

`workorder.json.operations` 是有序非空数组。每项必须有 `op` 和唯一目标 `id`。lookup 要求恰好命中一个元素，而不是“取第一个”。同一 ID 可以被多个有顺序的 op 修改，但每个 op 都必须产生实际变更。目标 ID 集合、前后 XML 与每项 change record 是审计依据。

| op | 必需字段 | 保留语义 |
|---|---|---|
| `set_text` | `id,text` | 只允许无子元素的文本节点，避免清空 tspan/混合内容；tail 不动 |
| `set_attribute` | `id,attribute,value` | 只改一个属性；不得改 ID/namespace/event，不允许多外部 href 或 JS/data HTML |
| `set_style` | `id,properties` | 对现有 inline style 做属性级 merge，未列出的 CSS 属性保留；可选 `remove` |
| `move_by` | `id,dx,dy` | 前置一个 translate，并保留已有 transform；dx/dy 必须有限数值，不可 bool |
| `replace_edge_kind` | `id,kind` | 仅 path/line/polyline；改 data-edge-kind、dash/marker 及该 kind 的明确颜色，不动 `d`、ID、source/target 几何 |

允许的 edge kind：`solid`、`direct`、`dashed`、`dotted`、`feedback`、`uncertain`。`direct/feedback/uncertain` 分别约定蓝/紫/琥珀色和本地 marker。替换 edge kind 不等价于证明机制关系；科学含义必须来自 workorder/source review。

## XML 与安全

- 禁止 DOCTYPE 与 ENTITY，避免外部实体等高风险结构。
- 每个元素（含 root、metadata、defs、容器）必须有稳定唯一 ID。没有 ID 的源不能盲目自动加 ID，因为那本身是非最小全局变更；先让人类/Agent 提供满足契约的源。
- Unicode 文本按原字符串写入；namespace prefix 注册保留；XML 声明/空元素格式可能标准化，审计针对语义和子树，不声称整个 XML 字节都未改变。
- set_style 拒绝 `url()`、`expression()`、`@import`、JavaScript、behavior 等危险 CSS。普通 fill/stroke/font/dash 属性可用于科学图。
- 所有输出先写同目录临时文件、flush/fsync，再 `os.replace`；输入原件仅在 backup 中被读取复制。

## 事务和 unchanged 证明

在内存 deep copy 上依序执行。任何一个 op、XML 比较或导出失败，不能留下本次最终 edited SVG/PNG/PDF。原件 SHA-256 在写前 manifest 和结束时各计算一次。

unchanged 比较有两层：

1. 每个非目标元素的 tag、attributes、direct text、tail 必须一致。target 的祖先若其直接内容未改，也在此层通过。
2. 非 target 且非 target 祖先的整个序列化子树必须一致。因此根层 hash 可以只因声明的后代编辑改变，而不能借“根变了”掩盖无关改动。

`unchanged_elements.json` 给出每个元素的 before/after SHA-256、target/ancestor 标记与比较策略。比较不是科学正确性的证明；方向、图例、标签语义仍由 Agent 审核。

## minimal new SVG helper

无源时 helper 创建白底、唯一 ID、metadata/title 和简单节点；不读取也不模仿 source.svg，不输出 source-preserving 成功声明。它拒绝覆盖输出，主要作用是提供一个以后可做安全 surgery 的最小可编辑源。
