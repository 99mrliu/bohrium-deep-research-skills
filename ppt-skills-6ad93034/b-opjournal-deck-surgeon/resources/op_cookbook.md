# 操作手册（op cookbook）

## 七种操作

| 操作 | 用途 | 关键字段 |
|-|-|-|
| add_slide | 末尾加页 | layout: title/body, role |
| set_title | 写页标题（页级主张） | slide, text |
| set_bullets | 整页重写要点（每条带 anchor） | slide, items |
| set_notes | 写演讲备注 | slide, text |
| insert_figure | 插入论文真实裁剪图 | slide, fig |
| remove_slide | 删除整页 | slide |
| replace_text | 页内局部精确替换（小修首选） | slide, find, by, anchor |

## 场景一：create 模式新建整稿（工单 N 页）

一轮 ops 完成骨架，一轮补图与备注：

1. N 个 `add_slide`（第 1 页 layout=title，其余 body）；
2. 每页 `set_title` + `set_bullets`；
3. 结果/方法页 `insert_figure`（只用 intake 打印的 figures_ok，图序与论文一致）；
4. 每页 `set_notes`（1–3 句，写给工单受众）。

## 场景二：edit 模式旧稿翻新

1. 先 `apply.py` 空放一次，确认底稿页数与结构（或直接用 python-pptx 只读查看，勿改）；
2. 对保留页：不动；对过时页：`set_bullets` 整页重写或 `replace_text` 局部替换；
3. 新增内容：`add_slide` 追加；废页：`remove_slide`（注意其后页码前移，同轮后续操作按删除后的页码写——稳妥做法是 remove 放最后一轮）；
4. 每页补 `set_notes` 与锚点（旧稿通常缺）。

## 场景三：局部修订（评审意见回复式）

只提交 `replace_text` / `set_notes` / `insert_figure` 小操作，why 里写明对应哪条意见。change_journal.md 即修订说明。

## 常见拒绝原因

- 数字未命中锚定页 → 核对论文原文写法，或把 anchor 改到数字实际所在页；
- bullet 超 6 条/超长 → 拆页或压缩；
- 图无裁剪 → 换 figures_ok 里的图；
- 忘写 why → 补上真实理由（"充实内容"不算，"补充 p8 主结果数据"算）。
