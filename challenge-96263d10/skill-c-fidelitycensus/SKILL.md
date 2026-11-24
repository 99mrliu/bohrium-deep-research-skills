---
name: fidelity-census-adaptation
description: 学术格式与模板适配——内容保真普查法（转得全）。格式可以全部重排，内容单元一个不许无声增减：把源稿与交付产物分别普查成有序文本单元+数字 token+引用 token+对象计数（图/表/公式/脚注/批注/超链接/域/书签）的内容清单，机器比对逐条定位差异，再用声明账本裁决——任务要求的改动必须有事前声明（unit/before/after/reason），未被声明覆盖的差异即为事故，拦截交付。支持 DOCX 与 Markdown/LaTeX/纯文本，纯 Python 3 标准库。适用于"格式转换后证明内容没丢没改""改稿留痕""交付前内容回归校验"类任务。
---

# 内容保真普查（fidelity-census：差异必须有名有姓）

版本 1.0。核心主张：适配质量的对立面不是"格式没改对"，而是**内容在
转换中被静默删除、合并、改写或图片化**。本 Skill 把内容保真做成强制工序：
普查 → 差异 → 声明覆盖，三件套缺一环不交付。单元口径与覆盖判定见
`references/fidelity-method.md`。

以下 `$SK` 指本 SKILL.md 所在目录（平台安装为 `/skills/weekly-skill`，先 `ls /skills/` 确认）。

## 运行契约（平台约定，必须遵守）

- 输入 `/input/case.json` + `/input/task.md` + 材料；先读任务再读材料实际内容。
- 工作目录 `/app/work`，交付 `/app/output`。
- `/app/output/result.json`：`case_id` + case.json `output_contract` **全部字段** +
  `status` + `sources` + `changes`（与声明账本同源）+ `uncertainties` + `limits` +
  `artifacts`（带 sha256）。有未裁决差异或未确认项就 partial。
- 预算约 900 秒：**第一步先落 partial result.json 骨架**，之后每阶段就地更新。
- Office 产物附真实渲染 PDF/PNG 预览；渲染不可用就在 limits 声明。

## 流水线（六步）

### 1. 源稿普查（动手之前）
```bash
python3 $SK/scripts/census.py /input/稿件.docx --out /app/work/census_src.json
```
得到内容清单基线。文本型材料（.md/.tex/.txt）同一命令。

### 2. 声明账本开工
```bash
python3 $SK/scripts/change_ledger.py init /app/work/ledger.json
```
账本先于改动存在；**先声明、后动手**。适配过程中每改一处内容性改动
（任务要求的数值更新、题注重写、文献条目规范化）立即 add 一条：
```bash
python3 $SK/scripts/change_ledger.py add /app/work/ledger.json \
    --unit "unit 1 / 表2 第3行" --before "0.85" --after "0.86" --reason "任务书第3条要求"
```
纯格式改动（样式、页边距、字体）不进账本——普查对它们天然免疫。

### 3. 适配执行（Agent 主导）
按任务要求完成格式适配，产出交付件到 /app/output。

### 4. 产物普查 + 差异裁决（对交付目录里的最终文件跑）
```bash
python3 $SK/scripts/census.py "/app/output/交付件.docx" --out /app/work/census_out.json
python3 $SK/scripts/census_diff.py /app/work/census_src.json /app/work/census_out.json --out /app/work/diff.json
```

### 5. 覆盖裁决
```bash
python3 $SK/scripts/change_ledger.py verify /app/work/ledger.json /app/work/diff.json
```
- COVERED（退出 0）：全部差异有声明，进第 6 步。
- UNDECLARED_CHANGES（退出 1）：逐条处理——是事故就修产物重跑 4–5；
  是漏声明的合法改动就补声明（补声明必须在 reason 里写清任务依据，
  不许写"忘了"）；判不定的进 manual_confirm。

### 6. 交付
diff.json、coverage 裁决、ledger.json 随产物进 /app/output；
result.json 的 changes 直接引用账本条目（seq 号）。

## 异常处理

| 情况 | 处置 |
|---|---|
| 输入格式不支持（非 docx/md/txt/tex） | census 退出 2；改人工比对并在 limits 声明"无机器普查" |
| 章节被任务要求重排 | 先声明"整章移动"再人工过 diff 余项；不许裸跑全等标准 |
| 公式 OMML↔LaTeX 互转 | 只数个数；语义等价性人工核对，进 manual_confirm |
| 图片被任务要求重绘 | 声明进账本；像素级一致性靠渲染目检，limits 声明 |
| 差异超过 20 处 | diff 自动截断并列 truncated：先修系统性原因（多半是流程错了），不是补 20 条声明 |
| 时间不足 | 骨架 → 源普查 → 适配 → 产物普查 → verify 最小链先交付 |

## 资源清单（均在 `$SK/` 下）

| 路径 | 作用 |
|---|---|
| `scripts/census.py` | 内容单元普查（DOCX/MD/TeX/TXT） |
| `scripts/census_diff.py` | 全等比对 + 差异逐条定位（单元号/token/对象名） |
| `scripts/change_ledger.py` | 声明账本 init/add/verify（覆盖裁决） |
| `references/fidelity-method.md` | 单元口径、覆盖判定、已知限制 |
| `examples/` | 合成示例：声明覆盖 PASS + 静默删改被拦截实录 |

## 自查清单（交付前）

1. 源/产物普查都是对最终文件跑的，sha256 与交付件一致。
2. verify COVERED；账本每条 reason 都指向任务依据。
3. manual_confirm 里列清机器判不定的项（公式语义、图片内容、重排合法性）。
4. result.json changes 与账本 seq 一一对应。
