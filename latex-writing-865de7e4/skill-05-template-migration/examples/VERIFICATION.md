# VERIFICATION — 本地端到端验收记录

> 合成示例（synthetic example）的验证记录，非正式案例结果。
> 仅证明本 bundle 的脚本接口可运行，不代表正式案例表现。

环境：macOS arm64；Python 3.12.14（仅标准库）；pdfTeX 3.141592653-2.6-1.40.29
（TeX Live 2026，`export PATH="$HOME/texlive/2026/bin/universal-darwin:$PATH"`
后可用）。运行目录 `examples/_run/`（input/work/output 三件套），验收后已
删除，只保留本文件、`sample_output/` 两份小型文本示意输出与示例输入。

## 1. 正常路径（迁入 mockjournal 的合成稿件）

```bash
B=<bundle 目录>
R="$B/examples/_run"; mkdir -p "$R"/{input,work,output}
cp "$B"/examples/{case.json,task.md,manuscript.tex,mockjournal.cls} "$R/input/"

python3 "$B/scripts/clsinspect.py"  --input "$R/input" --work "$R/work"
python3 "$B/scripts/pkgconflict.py" --input "$R/input" --work "$R/work"
python3 "$B/scripts/finalize.py" --input "$R/input" --work "$R/work" \
    --output "$R/output" --original "$R/input/manuscript.tex" \
    --migrated "$B/examples/migrated/manuscript_migrated.tex" \
    --cls "$R/input/mockjournal.cls"
```

观察到的关键输出：

- `clsinspect`：识别模板 `mockjournal`（基类 `\LoadClass[11pt]{article}`、
  类自带 geometry[margin=2.5cm]/booktabs/graphicx、禁用 titlesec）；
  必填项 `\journalname`、`\keywords` 在原稿中均判 **缺失**；章节映射表
  列出 2 个 `\section`；宏包差异表标出 geometry 选项不一致
  （Option clash 风险）及 booktabs/graphicx 重复。
- `pkgconflict`：共 4 条——[加载顺序] hyperref 在第 7 行加载但其后仍有
  booktabs/graphicx；[与模板类重复][error] geometry 选项 3cm vs 2.5cm；
  booktabs、graphicx 重复（warning）。每条附文件:行号与处置建议。
- `finalize`（对 `migrated/` 迁移稿）：

```
[finalize] 合规总结论：pass
[finalize]   必填 \journalname -> 已填
[finalize]   必填 \keywords -> 已填
[finalize]   编译：status=ran ok=True pages=1
[finalize]   正文文字改动：0 处
[finalize] result.json status=complete
```

- 编译为真实调用 pdflatex 有界两轮，构建目录内实际生成 **1 页 PDF**
  （按规范不随包提交二进制，仅在此记录）。
- `result.json` 目检：`case_id` 原样复制 `synthetic-migration-001`；
  契约方言识别为 `{type, required} 方言`；四个契约字段逐字段镜像
  （migrated_manuscript/compliance_report/intent_diff 指向真实文件，
  compile_ok=true）；`artifacts` 只列真实存在的 5 个文件；`uncertainty`
  为空。样本见 `sample_output/result.json`。
- `intent_diff.md`：原稿与迁移稿正文各 8 段，完全一致 8 段，**正文零
  文字改动**（导言区的文档类与宏包差异不计入正文）。

## 2. 降级场景一：迁移稿缺必填字段（必须判不合规，不放行）

用 `sed 's/^\\keywords{.*}$//'` 删掉迁移稿的 `\keywords` 行后重跑
finalize。观察到：

```
[finalize] 合规总结论：fail
[finalize]   必填 \keywords -> 缺失
[finalize]   编译：status=ran ok=False
[finalize] result.json status=partial
```

`blocking_issues` 同时列出「必填字段 \keywords：缺失」与真实编译错误
`! Class mockjournal Error: Missing required field: \keywords.`；
compliance 总结论为不合规，未放行。

## 3. 降级场景二：pdflatex 缺失（诚实降级）

以 `env PATH="/usr/bin:/bin"` 重跑 finalize：编译验证输出
`status=skipped ok=None`，result.json 中 `compile_ok=null`、status 降为
`partial`，uncertainty 注明「未探测到 pdflatex，编译验证诚实降级
（未执行）」。未假装编译成功。

## 4. 降级场景三：case.json 缺失

输入目录只放 manuscript.tex 与 mockjournal.cls 重跑 finalize：
`case_id=null`，uncertainty 首条为「case.json 缺失，已遍历输入目录降级；
发现文件：manuscript.tex, mockjournal.cls」，其余检查照常完成。

## 5. output_contract 四种方言归一化（单元级）

对 `normalize_contract` 直接喂四种方言验证：`{字段:{type,required}}` →
正确提取字段名/type/required（未把 `{type,required}` 当样例值输出成
`{}`）；字段名列表 → 字段名保留；JSON Schema（properties+required）→
字段与 required 标记正确；`- 字段名: 描述` 自然语言 → 启发式提取字段名并
注明需人工核对；无法提取的自然语言 → 原样保留于 contract_raw 并说明。

## 6. 运行约束检查

- 文件数：15（含本文件），≤ 50 且 ≤ 16 的目标规模；
- 总大小约 76 KB（≤ 2MB，≤ 300KB 目标）；单文件最大 finalize.py
  约 23 KB（≤ 500KB）；
- 全部文件 UTF-8 校验通过；无符号链接；无二进制（示例不提交 PDF，
  编译产物已随 `_run/` 删除）。
