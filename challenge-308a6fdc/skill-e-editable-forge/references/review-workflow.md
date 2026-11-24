# 人工复核工作流：在 Word 中逐条 accept/reject

`deliverable_tracked.docx` 里的修订是**真·Word 修订**（w:ins / w:del，
author = `skill-agent`），不是文字模拟。下面说明如何人工复核。

## 1. 在 Microsoft Word 中复核

1. 打开 `deliverable_tracked.docx`。
2. 功能区 **审阅（Review）** 选项卡：
   - **显示标记（All Markup）**：删除线 = 被删原文（w:del），下划线彩色 = 新插入（w:ins）。
   - 把光标放进任意修订，或点 **上一条 / 下一条（Previous / Next）** 逐条跳转。
3. 对每条修订点 **接受（Accept）** 或 **拒绝（Reject）**：
   - 接受 → 新文本留下，修订痕迹消除；
   - 拒绝 → 恢复原文。
4. 全部处理完后 **接受所有修订并停止修订（Accept All Changes and Stop Tracking）**，
   另存为正式稿。

WPS 文字操作相同（审阅 → 修订 → 接受/拒绝）。LibreOffice Writer：
**Edit → Track Changes → Manage…**，列表中逐条 Accept / Reject。

## 2. review_record.csv 的用法

`review_record.csv`（UTF-8 带 BOM，Excel 直接打开不乱码）是与 docx 修订一一对应的
**复核台账**：

| 列 | 含义 |
|---|---|
| 编号 | 与 edit_plan.json 中的顺序一致 |
| 类型 | 目前固定为 replace |
| 原文 / 新文 | find / replace 内容 |
| 理由 | 修改理由（来自 edit_plan） |
| 命中状态 | "命中" 或 "未命中：原文片段不存在 / find 为空" |
| 接受状态(accept/reject/留空待审) | **留空**，人工复核时填写 |

建议流程：

1. 先筛掉"命中状态 ≠ 命中"的行——这些修改**没有进入 docx**（脚本不做近似替换），
   需要人工判断是原文已变动还是 edit_plan 写错；
2. 对其余行，在 Word 中逐条 accept/reject，同时把决定回填到"接受状态"列；
3. 回填完的 CSV 就是本次改稿的审计记录，可与 forge_report.md、result.json 的
   change_log 互相印证。

## 3. 与验证报告的对应关系

- `forge_report.md` 第 2 节列出每条 edit 的命中/未命中；
- `result.json` 的 `change_log` 中 `status: "applied"` ↔ CSV"命中"，
  `status: "missed"` ↔ CSV"未命中"；
- `revision_stats.applied` 应等于 docx 中 w:ins（= w:del）的条数，
  可用 `python3 docx_forge.py verify --docx ...` 复核。
