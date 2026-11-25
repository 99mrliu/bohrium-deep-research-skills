# 方法说明：渲染契约、对账逻辑与设计取舍

## 1. 渲染契约（每份交付物必须保证什么）

上游解析把 PDF 变成"类型化 + 锚定"的块流之后，本 Skill 对交付物作出以下硬性承诺：

1. **完备性（completeness）**：每个输入块在 `deliverable.md` 与 `preview.html` 中
   各恰好出现一次。页眉页脚不得删除，只能移入附录并降低视觉权重。
2. **可回溯性（traceability）**：每个渲染出的块携带稳定锚点 `p{page}-b{seq}`，
   并能经 `anchor_map.json` 反查 page / column / bbox / kind。
3. **自包含（self-containment）**：`preview.html` 是单文件：`<meta charset="UTF-8">`、
   全部 CSS 内联于 `<style>`、无 `<script>`、无 `http(s)://` 引用、无外部字体。
4. **诚实性（honesty）**：渲染中的任何不完整（bbox=null、unresolved 文本缺失）
   都显式标注并进入 QC warnings；任何块丢失都使 QC fail，绝不静默。
5. **确定性（determinism）**：无时间戳、无随机数、无字典序依赖；同输入逐字节同输出。

## 2. 对账逻辑（render-QC 作为渲染回归测试）

```
blocks.jsonl ──计数──► N_in
anchor_map.json ──覆盖性──► 每个 block_id 恰有一个 anchor
deliverable.md ──正则 \[\[(p\d+-b\d+)\]\]──► 多重集合 M_md
preview.html ──正则 data-anchor="(p\d+-b\d+)"──► 多重集合 M_html
```

判定（全部满足才 pass）：

- `N_in == |anchors| == |M_md| == |M_html|`（计数对账）；
- `M_md` 与 `M_html` 作为**集合**等于 anchor_map 的锚点集（无 missing、无 extra）；
- 两个多重集合中任一锚点出现次数 >1 即 duplicated，fail；
- `anchor_map.schema_valid == true`。

失败语义：QC fail ⇒ `render_qc.json.status = "fail"`、`result.json.status = "failed"`
并附 `handoff`（交还上游解析/渲染步骤，禁止消费这些交付物）。**宁可误报不可漏报**：
对账是唯一防线，肉眼浏览不能替代。

警告语义（不 fail，但必须披露）：bbox=null 的块、unresolved 块写入
`render_qc.json.warnings` 与 `result.json.uncertainty`。

## 3. 为什么必须是自包含 HTML

- 审阅场景通常在隔离/离线环境：评审笔记本、内网机器、归档后的容器。任何外部
  CSS/JS/字体都会让"打开检查"依赖网络，违反交付物的根本目的。
- 单文件便于归档与 diff：一次渲染 = 一个文件，可用校验和固化。
- 无 JS 依赖同时消除了脚本注入面：块文本全部 HTML 转义后纯 CSS 呈现。
- 可访问性：锚点同时出现在 `id`（支持 `#p2-b7` 直达）与 `data-anchor`（支持机器
  回读对账）；`title` 属性让鼠标悬停即可看到 page/bbox/kind，无需切换工具。

## 4. 设计取舍

- **锚点命名 `p{page}-b{seq}`**：seq 按页内输入顺序递增。优点是稳定、可读、
  页内唯一；代价是上游块顺序变化会整体改号——因此锚点只在单次渲染会话内承诺稳定，
  跨版本对比应以 block_id 为准。
- **页眉页脚入附录而非删除**：保持完备性承诺的同时不干扰阅读流；HTML 中以
  opacity 0.45 置灰，Markdown 中以附录列表呈现。
- **Markdown 中公式用行内代码、HTML 用等宽字体**：不做 TeX 排版（需要 JS/MathJax，
  违反自包含）；保留原文即保留可核对性。
- **HTML 有效性**：输出为良好形成的 HTML5 子集（doctype、head/meta/style、
  body/nav/main/section/div），浏览器与常见解析器均可直接打开。

## 5. 限制

- 单文件 HTML 对超大文档（数千块）线性增长；建议分章渲染 + 分片 QC 后汇总。
- 锚点不编码列内阅读顺序之外的语义；复杂跨栏重排属于上游解析职责。
- 不验证文本内容与 PDF 原文的一致性（引用核对属于另一个 Skill 的范畴）。
- 不处理图片/矢量化区域本体；unresolved 块仅以占位 + 原因呈现。
