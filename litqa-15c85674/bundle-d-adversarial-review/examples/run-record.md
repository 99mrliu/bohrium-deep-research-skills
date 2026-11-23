# 最小调用示例运行记录（合成示例，非正式案例结果）

> 输入 `synthetic-case.json` 为虚构论文（SYN-2026-EnvCat-21，Bi2WO6/BiOI 异质结
> 光催化，7 个段落、2 个复合中文问题；**故意内置**摘要 91.8% 与正文 92.5% 的
> 数值冲突）。以下两轮运行均真实执行。

## 第一轮：草稿 → 审核（命中三类错误）

```bash
python3 scripts/review_loop.py prepare --case examples/synthetic-case.json \
    --work work/app/work --out work/app/output
# stdout: prepare ok: 2 draft(s), skeleton written

# （模型写 drafts/Q1.md、Q2.md；首轮故意含：虚构数值 95%、含糊比较"性能更高"、
#  冲突论断缺第二处引文）

python3 scripts/review_loop.py audit --work work/app/work
# stdout: audit done: 6/9 claims pass
# audit.md 节选：
#   Q1-C2 [REVISE] F2: 论断数值 92.5 未出现在引文中   （冲突论断只挂了 P1）
#   Q1-C3 [REVISE] F4: 比较措辞但引文取值不足两个      （"复合材料性能更高"）
#   Q2-C5 [REVISE] F2: 论断数值 95 未出现在引文中      （虚构数值）

python3 scripts/review_loop.py render --work work/app/work \
    --out work/app/output --legacy work/app/answers.json
# stdout: render ok: 6 claims delivered, status=partial
# 未过审的 3 条论断被机械降级为 unanswered_parts，附审核原因——诚实 partial。
```

## 第二轮：修订 → 复审 → 渲染（全 pass）

```bash
# 修订：冲突论断补挂 P3 引文；比较论断改为 inferred 并挂双取值；95% 改为有引文的论断
python3 scripts/review_loop.py audit --work work/app/work
# stdout: audit done: 9/9 claims pass
python3 scripts/review_loop.py render --work work/app/work \
    --out work/app/output --legacy work/app/answers.json
# stdout: render ok: 9 claims delivered, status=completed
```

## 产物

- `audit.synthetic.md`：第二轮审核报告（9/9 pass）；
- `result.synthetic.json`：最终渲染输出，`status=completed`，两题均 answered；
  摘要-正文数值冲突以一条挂双证据的论断并列保留。
