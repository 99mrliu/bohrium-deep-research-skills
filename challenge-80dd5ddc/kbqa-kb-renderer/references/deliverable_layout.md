# 交接包布局契约（deliverable layout）

交接包的读者是**没有参与过程的第三方**：他打开 knowledge_index.md 起，
三分钟内应能定位任何文件、任何答案及其证据。

## 目录布局

```
/app/output/
  result.json               # 主结果（case_id + contract 字段 + 诚实状态）
  render_report.json        # 机检报告（pass 字段为唯一权威结论）
  handover/
    knowledge_index.md      # 入口：文件树 + 版本说明链接 + 问题→答案卡索引
    catalog.csv             # 全文件清单（机器可读，列定义见下）
    version_notes.md        # 重复副本、版本标记、不可读文件的并列说明
    answers/q_<id>.md       # 每题一张答案卡
```

## catalog.csv 列

file_id, relpath, suffix, size, sha256_8, text_status, n_lines,
duplicate_of, version_tag。每行对应库内一个真实文件；sha256_8 为版本坐标；
text_status 非 ok 的行表示该文件不可作为证据。

## 答案卡规范

- 标题即问题编号；**答案**段先给结论，不确定就写"库中无依据"。
- 论断与证据段：每条证据格式固定为
  `` `[Fxx|sha8|La-Lb]`："逐字引文"（源文件：路径） ``，
  该格式会被 link_check.py 逐条回验，写错格式等于未给证据。
- 不确定性段：证据缺口、冲突、版本注意事项，逐条列出。
- 卡尾必须有返回知识库地图的链接（机检查互链）。

## 渲染纪律

- 渲染只重组编目与 answers.json 中已有内容，**不新增事实**；渲染阶段
  发现答案缺证据，回到问答阶段补，而不是在答案卡上手写。
- 所有 Markdown 相对链接必须指向包内真实文件；link_check 不过不许交付。
- catalog.csv 由 render_kb.py 从编目生成，禁止手工编辑（手工改动会被
  link_check 的磁盘重算抓出）。
