# 验收记录（合成示例（synthetic example），非正式案例结果）

本文件记录 bundle 的本地端到端验收：实际运行的命令与观察到的输出摘要。
示例工程为自造合成示例，仅证明接口可运行，不代表正式案例表现。
运行中间产物（`examples/_run/`，含编译生成的 PDF）验收后已删除；保留的
`sample_outputs/` 为真实运行产出的文本副本，头部均带合成示例标注。

## 环境

- macOS arm64，Python 3.12.14
- TeX Live 2026（`export PATH="$HOME/texlive/2026/bin/universal-darwin:$PATH"` 后
  pdflatex 3.141592653-2.6-1.40.29 / bibtex / biber 可用）

## 1. citeaudit 在坏工程上标出全部 5 类问题

```bash
python3 scripts/citeaudit.py --project examples/bad_project \
    --work examples/_run/work_bad \
    --banner "> 合成示例（synthetic example），非正式案例结果"
```

退出码 0。观察到的概要输出：

```
[citeaudit] 完成：6 个引用点，未定义引用 2，未定义交叉引用 0，重复 label 1，
未被引用 bib 条目 1，字段问题条目 5（其中缺必需字段 1）
```

报告逐条命中（完整文本见 `sample_outputs/citation_report_bad.md`）：

1. 未定义引用 `vaswani2017attentoin`（main.tex:17），候选
   `vaswani2017attention`（相似度 0.95，强匹配）；`zhang2020residual`
   （main.tex:19）无候选；
2. 重复 `\label{sec:intro}`（main.tex:16 与 main.tex:22）；
3. 未被引用条目 `knuth1984texbook`（refs.bib:35）；
4. `he2016deep` 缺必需字段 `year`（其余条目仅缺建议字段，如实区分）；
5. 正常引用 `vaswani2017attention` / `goodfellow2016deep` / `lecun2015deep`
   均解析到真实条目（file:line 在图谱中）。

## 2. citebuild 在坏工程上收敛但暴露未解析引用

```bash
python3 scripts/citebuild.py --project examples/bad_project \
    --work examples/_run/work_bad --build-dir examples/_run/build_bad \
    --engine pdflatex --max-rounds 6
```

退出码 2（有未解析引用，不静默忽略）。警告轮次曲线（未定义引用 /
未定义交叉引用 / 重复标签）：轮1 `6/2/0` → 轮3 `6/2/1` → 轮4 `2/0/1` →
轮5 `2/0/1`，相邻两轮集合相同，判定收敛。`.blg` 提取到
`I didn't find a database entry for "vaswani2017attentoin"`、
`... "zhang2020residual"`、`empty year in he2016deep`。最终键状态：
4 个正常键 resolved；`vaswani2017attentoin` 与 `zhang2020residual`
为 `unresolved（缺条目（bib 数据库中不存在该键））`。

注：坏工程初版为中文正文，pdflatex 报 Unicode 字符错误（rc=1）但引用
警告提取与收敛判定仍正常工作；后为使修复版可零错误编译，示例工程改为
英文正文，问题结构不变。

## 3. fixed 版真实多轮编译收敛到零

```bash
python3 scripts/citeaudit.py --project examples/fixed_project --work examples/_run/work_fixed
python3 scripts/citebuild.py --project examples/fixed_project \
    --work examples/_run/work_fixed --build-dir examples/_run/build_fixed \
    --banner "合成示例（synthetic example），非正式案例结果"
```

citeaudit 退出码 0：未定义引用 0、重复 label 0、未被引用条目 0、缺必需
字段 0（`he2016deep` 已补 `year`）。citebuild 退出码 0，pdflatex/bibtex
每轮 rc 均为 0；警告曲线：轮1 `5/2/0` → 轮3 `5/0/0` → 轮4 `0/0/0` →
轮5 `0/0/0`，第 4–5 轮集合相同，收敛。每个引用键最终状态（见
`sample_outputs/rounds_fixed.json`）：`goodfellow2016deep`、`he2016deep`、
`knuth1984texbook`、`lecun2015deep`、`vaswani2017attention` 全部
`resolved`。实际运行生成了 2 页 PDF（`build_fixed/main.pdf`，二进制未保留）。

## 4. finalize 装配与契约归一化

```bash
python3 scripts/finalize.py --case examples/case.json --input-root examples \
    --work examples/_run/work_fixed --out examples/_run/output_fixed \
    --project examples/fixed_project \
    --banner "> 合成示例（synthetic example），非正式案例结果"
```

观察到的 `result.json`（摘要）：`case_id` 原样为
`synthetic-citation-convergence-001`；output_contract（`{字段:{type,required}}`
方言）四个字段全部镜像为真实值——`citation_map`/`citation_report`/`rounds`
指向对应产物文件，`unresolved_citations` 为 `[]`；`status: complete`；
`uncertainty: []`；`artifacts` 只列真实存在的 5 个文件。
`citation_map.md` 逐行列出 6 个引用点 ↔ `refs.bib` 条目行号 ↔ `resolved`。

契约方言归一化单测（`normalize_contract`）：`{a:{type,required}}`、字段名
列表、JSON Schema（properties/required）、自然语言反引号描述四种输入均
正确还原为字段清单，未出现把 `{type,required}` 当样例值输出成 `{}` 的问题。

## 5. 降级场景（诚实降级验证）

- **无 bibtex/pdflatex**：`env PATH=/usr/bin:/bin python3 scripts/citebuild.py ...`
  → 退出码 3，`rounds.json` 写入
  `status: compile_unavailable` 与说明「编译验证不可用：缺少 pdflatex；
  缺少 bibtex。静态审计（citeaudit.py）结果仍然有效。」；同环境下
  citeaudit 退出码 0，静态报告照常产出。
- **case.json 缺失**：finalize 遍历输入根目录记录文件清单，`case_id` 为
  null，`status: partial`，uncertainty 记录「case_id 不可得（case.json
  缺失）」，不谎称 complete。

## 6. 运行约束检查

- 文件数 16（≤50 且 ≤16 目标达成）；无符号链接；无二进制（示例不提交
  PDF，PDF 在验收运行时生成并已删除）。
- 全部文件 UTF-8/ASCII 文本；单文件最大 27 KB（scripts/citeaudit.py），
  总计约 75 KB（≤500KB/单文件、≤2MB 总量、≤300KB 目标均满足）。
- 脚本仅依赖 Python3 标准库（`import` 仅 argparse/difflib/json/os/re/
  shutil/subprocess/sys）。
