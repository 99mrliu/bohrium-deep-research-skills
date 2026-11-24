# notes-quality.md — 备注三要素、反模式与门禁口径

## 1. 备注三要素

每页备注（= 该拍讲稿）必须包含：

1. **过渡（transition）**：引向下一拍的一句话。notes_lint 通过标记词表检测
   （next / moving on / turning to / finally / however / in summary / 接下来 /
   最后 / 然而 …… 完整表见 `notes_lint.py` 的 `MARKERS`）。
2. **强调（emphasis）**：本拍希望听众记住的一点，常用 "remember" / "note that" /
   "key point" / "请注意" 引出。过渡与强调标记满足其一即通过门禁，但好讲稿两者都有。
3. **备询证据（if-asked）**：以 "If asked ..." 开头的补充，给出答案要点并指回论文
   页码（figure/table/anchor + page）。答辩场景的质量主要在这里体现。

slide_forge 把备注组织为：

```
<beat_text 逐字讲稿>

[TRANSITION] <过渡句>

[IF-ASKED] <备询补充>
```

## 2. 反模式（门禁或人工评审都会抓）

1. **复读**：备注 = 页面文字复制粘贴。notes_lint 用 token Jaccard 检测，
   >0.5 即 error（实测复读 deck 的 Jaccard 为 1.00，14 个 error，退出码 1）。
2. **缺失**：整页无备注 → `notes_missing` error；make_result 的 notes_coverage
   随之失败。
3. **剧透下一页**：过渡句把下一拍的结论和盘托出（"Next I will show that X improves
   by 37%"）。门禁不抓这个，靠人工评审；写过渡句只给方向、不给结论。
4. **超时备注**：单拍讲稿远超均摊时长。rehearse 把 >1.5× 均摊的页列为 over_speed，
   <15 秒的列为 thin（均为 warning，不阻断，但应在 change_records 里说明处置）。
5. **无出处断言**：备注里给出论文中不存在的数字。用 evidence.json 的锚点交叉核对；
   页面引用必须能在 evidence.json 找到（beat_cut 门禁）。

## 3. 门禁口径（notes_lint.py）

| 检查 | 阈值 | 级别 |
| --- | --- | --- |
| 每页备注非空 | — | error |
| Jaccard(备注, 页面可见文字) | ≤ 0.5（--max-jaccard 可调） | error |
| 过渡/强调标记 | ≥1 个 MARKERS 命中 | error |
| 总口播时长（CPM/WPM 估算） | ≤ 分钟预算 | error |

退出码：任一 error → 1；文件不可读 → 2；全过 → 0，并输出逐页表格与
notes_report.json（含每页 jaccard、spoken_sec、problems）。
