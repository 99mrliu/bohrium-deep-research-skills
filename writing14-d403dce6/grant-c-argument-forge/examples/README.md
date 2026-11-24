# 合成示例与真实运行记录（grant-c-argument-forge）

> 合成示例，非正式案例结果。本目录所有输入均为虚构材料；下述命令与输出为**真实执行**
> 的记录（macOS / Python 3.9，仅标准库），运行产物统一写到 bundle 之外的
> `writing14/example-runs/grant-c-argument-forge/`。

## 一、示例输入

| 文件 | 说明 |
|---|---|
| `proposal_sections.md` | 陷阱版章节稿：2 句口号（无引文）、「国际领先」「填补空白」各一处、创新点第 2 条无差异定位且不点名已有工作、1 处事实句无引文、论证链缺“差距”角色 |
| `proposal_sections_fixed.md` | 修复版：口号句改为带引文事实句或删除、修饰改为可核验表述、补齐“差距”句、事实句全部带引文、创新点第 2 条补齐四要件 |
| `existing_works.json` | 虚构已有工作清单（名称/方法/局限），供 innovation_diff.py generate 演示 |
| `diff_table_filled.md` | 填了一半的差异定位表，陷阱：第 2 行“难点”为空单元格 |
| `diff_table_fixed.md` | 修复版差异定位表，全部单元格填写完整 |

## 二、真实运行记录

设 `B=bundles/grant-c-argument-forge`，`R=example-runs/grant-c-argument-forge`。

### 1. 陷阱版：修辞 Lint 抓到 L1×2、L2×2、L4×1，退出码 1

```
$ python3 $B/scripts/rhetoric_lint.py $B/examples/proposal_sections.md -o $R/trap
rhetoric_lint: 5 error, 0 warning -> .../trap/lint_report.json
  L1: 2 error, 0 warning
  L2: 2 error, 0 warning
  L4: 1 error, 0 warning
exit=1
```

`lint_annotated.txt` 关键标注（带行号）：

```
   9 | 技术势在必行。该方向对保障国家能源安全具有重要意义。目前工业合成氨主要采用
     ^ [L2 error] 口号句：含政策口号模式「势在必行」且句内无引文标记
     ^ [L2 error] 口号句：含政策口号模式「具有重要意义」且句内无引文标记
  14 | 设计上积累十年经验（申请人前期工作，2021），相关成果达到国际领先水平。为此，本研究拟
     ^ [L1 error] 命中不可核验修饰词禁用表：「国际领先」
  16 | 方向尚属空白，本研究将填补空白。
     ^ [L1 error] 命中不可核验修饰词禁用表：「填补空白」
  24 | 2. 构建大规模等离子体催化反应数据集：该数据集体量大、维度全，构建过程面临标注一致性
     ^ [L4 error] 创新点第 2 条四要件不全，缺：差异定位（不同于/区别于/相比/而现有 等）；点名已有工作（作者年份/《成果名》/文献编号）
```

### 2. 陷阱版：论证链缺“差距”角色，退出码 1

```
$ python3 $B/scripts/argument_map.py $B/examples/proposal_sections.md -o $R/trap
argument_map: 句子 9 句；链完整=False（缺失：差距；次序合理=False）；事实句引文覆盖率 0.80/0.80；未分类 1 句
exit=1
```

`argument_map.json` 中角色序列：口号、口号、现状、瓶颈、已有进展、现状（无引文，陷阱）、
团队凭据、切入点、未分类（即“填补空白”句）。链必要角色“差距”缺失，判定不通过。

### 3. 差异定位表：生成模板，退出码 0

```
$ python3 $B/scripts/innovation_diff.py generate $B/examples/existing_works.json -o $R/generate/diff_table_template.md
innovation_diff generate: 已生成 .../generate/diff_table_template.md（2 项已有工作，2 个候选创新点）
exit=0
```

模板按候选创新点各生成一张表，`其局限(引原文)` 由 JSON 预填并加引号，其余三列为
`【待填】` 占位。

### 4. 陷阱版：已填表存在空单元格，退出码 1

```
$ python3 $B/scripts/innovation_diff.py check $B/examples/diff_table_filled.md -o $R/trap
innovation_diff check: 表格 1 张，error 1 处
  行 11: 第 1 张表：第 11 行「难点」为空单元格
exit=1
```

### 5. 修复版：三项检查全部通过，退出码 0

```
$ python3 $B/scripts/rhetoric_lint.py $B/examples/proposal_sections_fixed.md -o $R/fixed
rhetoric_lint: 0 error, 0 warning -> .../fixed/lint_report.json
exit=0

$ python3 $B/scripts/argument_map.py $B/examples/proposal_sections_fixed.md -o $R/fixed
argument_map: 句子 8 句；链完整=True（缺失：无；次序合理=True）；事实句引文覆盖率 1.00/0.80；未分类 0 句
exit=0

$ python3 $B/scripts/innovation_diff.py check $B/examples/diff_table_fixed.md -o $R/fixed
innovation_diff check: 表格 1 张，error 0 处
exit=0
```

### 6. 确定性验证

对同一输入连续运行两次 `rhetoric_lint.py`，`lint_report.json` 与 `lint_annotated.txt`
逐字节一致（cmp 无差异），退出码均为 1。

## 三、排查提示

- L4 报“未找到标题含「创新点」的小节”：章节稿需有标题文字含“创新点”的小节标题。
- argument_map 报句子数异常多：多为 PDF 拷出文本的硬换行所致，脚本已按 。！？； 切句，
  换行不断句；若材料为逐行断句（无句读），请先合并。
- check 报“未发现任何 markdown 表格”：表格行须以 `|` 开头且含表头、分隔行、数据行。
