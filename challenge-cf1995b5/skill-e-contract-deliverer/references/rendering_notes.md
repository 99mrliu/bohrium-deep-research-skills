# 渲染降级策略（rendering notes）

render 子命令的产物层级与降级规则：

1. **plan.md（必有）**：plan.json + result.json 渲染的人读件，含六要素章节、
   成本可重算表、校验摘要表、确认项清单。即使 plan.json 缺失也会渲染出带 TODO
   的 plan.md 并明确提示——绝不静默失败。
2. **plan.pdf（尽力而为）**：
   - 检测到 `pandoc` → `pandoc plan.md -o plan.pdf`；
   - 否则检测到 `libreoffice/soffice` → headless 转换；
   - 都没有 → **不生成 PDF**，并把原因如实追加进 `result.json` 的 `uncertainty`：
     "未生成 PDF 预览：运行环境未检测到 pandoc 或 libreoffice/soffice；
     plan.md 为最终人读件，内容不因此缺失。"
   - 导出命令异常（超时/非零退出）同样降级为文字说明，不谎报成功。
3. **绝不造假**：不存在"生成一个空 PDF 占位"或"在 result.json 里写已生成 PDF"
   的做法。评审要的是诚实 status，不是好看的状态。

## 评审视角的交付清单（按优先级）

| 优先级 | 产物 | 说明 |
| --- | --- | --- |
| P0 | result.json | 合法 JSON、字段齐、status 诚实；scaffold 后立即就位 |
| P1 | validation_report.json | validate 输出，PASS/FAIL 逐项 + 修复指引 |
| P2 | plan.md | 人读件，六要素 + 校验摘要 |
| P3 | plan.pdf | 有工具则导出，无则 uncertainty 如实记录 |
| P3 | plan_skeleton.md | scaffold 产物，过程痕迹 |

## 900 秒时间盒下的渲染节奏

- T0：scaffold（秒级）→ 已有合法 partial。
- 中段：每 fill 完一批字段就 validate 一次（<5 秒），报告即修复指引。
- 收尾前 ≥60 秒：最后一次 validate + render，保证 plan.md 与最终 result.json 同步。
- 任何时刻被截断：/app/output 里的 result.json 都是 status 诚实的合法交付。
