# 预算协议 — 红队轮次与先存后优

平台预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens。
红队复核的检测器全部是确定性脚本（零模型请求），模型预算只花在
**撰写 deck、人工修复、裁决理由** 上。

## 轮次预算

| 轮次 | 范围 | 模型请求 | 说明 |
|------|------|----------|------|
| Round 1 | 全量 R1–R8 | 0（脚本） | 检出即入账 |
| 处置 | 自动修 + 人工修 | 每条人工 finding 1–2 次 | 机器修 0 请求 |
| Round 2 | 全量复扫 | 0（脚本） | 验证收敛 |
| Round 3（可选） | 定向复扫 | 0（脚本） | 仅当门禁 fail 且预算充足 |

- **≤2 轮全量**；第 3 轮只允许定向（重扫修复涉及的页，即重跑
  redteam_scan 但只对比相关 slide 的 finding）。
- 每轮扫描秒级完成，不吃 900 秒墙钟预算。

## 先存后优检查点

1. **T+0**：extract_facts → facts.json 落盘（一切后续工作的锚点）。
2. **T+deck v1**：第一稿 deck.json 落盘即扫描入账——宁可是带病稿，
   不要在内存里打磨。
3. **T+处置**：apply_fixes 落盘 deck_fixed.json + fixes_report.json。
4. **T+收敛**：convergence.json 落盘后才允许 build_deck。
5. **T+交付**：build_deck → make_result（含真实渲染）。任何后续优化
   不得破坏已落盘的 result.json；优化失败随时可回滚到该检查点。

## 异常速查

| 异常 | 处理 |
|------|------|
| PDF 加密/扫描件 | extract_facts 退出码 2；result.json exceptions 记 tool_missing，报 partial |
| 图抽不出 | build_deck 记 figures_missing + warnings；deck 保留文字引用，不伪造图 |
| 公式为图片 | 不入数值锚点池；相关 claim 必须走 caption/文字引用 |
| 模板占位符不足 | build_deck 回退版式并记 warnings；空占位符一律移除 |
| 字体缺失 | 渲染仍进行（LibreOffice 替换字体）；在 uncertainties 声明 |
| 页数超限 | 先删可 disposition 的 warn 页？——禁止。应合并内容页，重扫后再收敛 |
| 预算将尽 | 当前轮 finding 全量入账后即停：converge_gate 出 verdict，fail 则报 partial 并附台账 |
