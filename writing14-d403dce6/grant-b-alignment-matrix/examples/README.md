# examples：合成示例与真实运行记录

**合成示例，非正式案例结果。** 本目录只含合成输入；示例运行产物按约定写到
bundle 之外：`writing14/example-runs/grant-b-alignment-matrix/`。
下列命令与输出均为 2026-11-24 在本仓库真实执行的结果（未伪造）。

## 1. 合成输入

| 文件 | 说明 |
| --- | --- |
| workorder.json | 虚构组织方要求：七要素清单 + Q/G/C/R/K 编号与一致性约束 |
| proposal_sections.md | 含四类陷阱缺陷的章节稿（见下） |
| consistency_matrix.json | 与缺陷稿一致的矩阵（保留两处矩阵内缺陷） |

陷阱缺陷设计：

1. 研究内容 C3 没有任何技术路线步骤覆盖（矩阵缺 R→C3 边）→ 应触发 M2；
2. 考核指标 K1 的边挂到不存在的 G4（K1→G4）→ 应触发 M4；
3. 正文出现「拓展 C4」而矩阵未登记 C4 → 应触发 M5（反向）；
4. 章节稿缺「创新点」标题 → 应触发 M6。

## 2. 真实运行命令与结果

以下命令在工作目录 `writing14/` 下执行；`$B` 指
`bundles/grant-b-alignment-matrix`，`$R` 指 `example-runs/grant-b-alignment-matrix`。

### 2.1 生成计划与空矩阵模板

```
python3 $B/scripts/matrix_scaffold.py --workorder $B/examples/workorder.json --outdir $R
```

退出码 0。关键输出（真实摘录）：

```
matrix_scaffold.py 1.0 完成
  要素来源：workorder.writing_requirements.elements_required（7 项）
    1. 立项依据 … 7. 研究基础与可行性
  一致性约束线索：1 条
  已写出：example-runs/grant-b-alignment-matrix/plan.json
  已写出：example-runs/grant-b-alignment-matrix/consistency_matrix.template.json
```

（对不含要素清单的输入，scaffold 回退到 SPEC 默认七要素并标注
`要素来源：spec_default`，已实测。）

### 2.2 缺陷版回检（陷阱必须被抓住）

```
python3 $B/scripts/matrix_check.py --matrix $B/examples/consistency_matrix.json \
  --draft $B/examples/proposal_sections.md --plan $R/plan.json \
  --report $R/check_report.booby.json
```

退出码 **1**。真实输出全文：

```
matrix_check.py 1.0：error=4 warning=0
  [M2][error] 研究内容 C3 没有任何技术路线步骤覆盖（缺 R->C）
  [M4][error] 悬空引用：边 K1->G4 指向未登记的 ID G4
  [M5][error] 正文出现的编号 C4 未登记进矩阵（研究内容类）
  [M6][error] 七要素标题缺失：未找到『创新点』（含别名：创新点、特色与创新、创新之处、项目特色与创新）对应的 markdown 标题
  报告已写出：example-runs/grant-b-alignment-matrix/check_report.booby.json
结果：不通过（存在 error 级发现）
```

四类陷阱各被抓到一条，无误报；报告全文见
`example-runs/grant-b-alignment-matrix/check_report.booby.json`。

### 2.3 修复版（exit 0）

修复动作（稿矩阵同步改）：

- 章节稿：新增「六、创新点」章节；技术路线新增步骤 R3（对应 C3），计数句
  改为「技术路线包含 3 个步骤」；删除「拓展 C4」表述；
- 矩阵：新增节点 R3 与边 R3→C3；K1 的边由 K1→G4 改为 K1→G3。

修复版文件位于 `example-runs/grant-b-alignment-matrix/`：
`fixed_proposal_sections.md`、`fixed_consistency_matrix.json`。

```
python3 $B/scripts/matrix_check.py --matrix $R/fixed_consistency_matrix.json \
  --draft $R/fixed_proposal_sections.md --plan $R/plan.json \
  --report $R/check_report.fixed.json
```

退出码 **0**。真实输出：

```
matrix_check.py 1.0：error=0 warning=0
  报告已写出：example-runs/grant-b-alignment-matrix/check_report.fixed.json
结果：通过
```

### 2.4 渲染要素对照说明表

```
python3 $B/scripts/matrix_render.py --matrix $R/fixed_consistency_matrix.json \
  --out $R/matrix_appendix.md
```

退出码 0。产物 `matrix_appendix.md`（可直接嵌入章节稿附录）真实内容要点：

```
| Q 科学问题 | G 研究目标 | C 研究内容 | R 技术路线步骤 | K 考核指标 |
| Q1 | G1 … | C1 … | R1 | — |
| Q1 | G2 … | C2 … | R2 | — |
| Q2 | G3 … | C3 … | R3 | K1 |
- 节点计数：Q=2，G=3，C=3，R=3，K=1；边数=10
- 被目标回应的科学问题：2/2；被内容支撑的研究目标：3/3；被路线步骤覆盖的研究内容：3/3
```

对缺陷矩阵渲染（`$R/matrix_appendix.booby.md`）时，C3 行 R 列显示
「—（缺路线步骤）」，覆盖统计显示「被路线步骤覆盖的研究内容：2/3」，
缺陷在附录层面同样可见。

### 2.5 其他实测行为

- 确定性：同一命令二次运行，报告 JSON 与标准输出字节一致（cmp 通过）。
- 矩阵 JSON 损坏：按 M1 报 error，退出码 1。
- 正文计数句与矩阵不符（如「研究目标共 4 个」对 3 个 G）：M8 error，退出码 1。
- 缺输入文件 / 未给 --case 与 --workorder：退出码 2。

## 3. 复现方式

按第 2 节命令原样执行即可复现全部退出码与输出；脚本仅用 Python3 标准库，
无网络与环境依赖，输出不含时间戳。
