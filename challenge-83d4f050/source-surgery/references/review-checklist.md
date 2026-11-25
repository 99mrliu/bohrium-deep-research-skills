# Native scientific and visual review checklist

脚本完成后按顺序记录，不能用“机器退出 0”代替：

## 来源与科学含义

- [ ] 阅读实际原文/图注、原始 SVG、figure03 PNG、data 和 workorder；sources 逐项有 SHA-256。
- [ ] 每个变更都是 source/workorder 授权的最小编辑，没有为了“美观”重画整图。
- [ ] label 的术语、edge kind、source/target 方向、feedback/uncertain 语义与原数据一致。
- [ ] 若无真实源且用了 minimal helper，交付明确标为 minimal-new-source，没有虚假 preservation 声明。
- [ ] 模拟/SYNTHETIC 内容不会被描述为生物学验证或实际科研结论。

## 可编辑源完整性

- [ ] before/after XML 都存在；根与所有元素 ID 不新增、不删除、不重复。
- [ ] change_records 数量、顺序和目标与 workorder 一致，无 no-op。
- [ ] unchanged report 每一非目标直接内容一致；非目标非祖先子树完整一致。
- [ ] metadata、title、desc、defs、未目标 text、保护层、note 可在 after XML 回读。
- [ ] 原 SVG SHA-256 全程不变，backup hash 一致，输出路径未覆盖输入。

## 实际 PNG/PDF 目检

- [ ] 用图像输入真正查看本次 edited PNG，而非仅查看文件大小。
- [ ] PDF 用 PyMuPDF 验证一页、提取文本，并渲染该页再次目检。
- [ ] 标签不溢出/不截断；edge 标签与线不重叠；feedback 仍清晰；uncertain 在可见文字与 SVG 属性中都保留。
- [ ] 与 before 对照：未请求的颜色、位置、方向、layer、legend、保护层没有视觉改变。
- [ ] 记录 renderer/font/dash/marker 等限制。某些 PyMuPDF 版本可能弱化 dash 或 marker 的可见效果；必须如实披露，而不是假定所有 viewer 一致。
- [ ] attest 的 observation 是本次图像中可观察的事实，limitation 不为空；hash 失败或科学疑问则降级，不标 complete。

完成条件不是“有 PNG”，而是所有动态字段/文件、来源、内容映射、不确定性、change records 与真实视觉审核同时成立。
