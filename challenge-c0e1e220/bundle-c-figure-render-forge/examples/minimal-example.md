# 最小示例（**合成示例**，非真实数据）

本示例演示 bundle C 的完整链路：合成三组小样本数据 → 一键 baseline → SVG 兜底渲染 → 机器审计 → 埋雷拦截。

## 输入（由 make_synthetic.py 现场生成）

- `response.csv`：`group,rt` 两列，control(n=8) / treatA(n=9) 正态，treatB(n=10) 右偏，seed=20240501 固定。
- `case.json`：标注 `SYNTHETIC 合成示例`；`task.md`：要求按 group 比较 rt（ms）。

## 调用

```bash
bash examples/run_example.sh
```

脚本依次执行并自断言：

1. `make_synthetic.py --out $TMP/input` 生成合成数据；
2. `pipeline_c.py run --input $TMP/input --work $TMP/work --output $TMP/output`；
3. `figure_forge.py --work $TMP/work --output $TMP/output --force-svg`（不依赖 matplotlib 的 SVG 通道）；
   断言：SVG 文件生成、`<svg` 签名有效、figures.md 图注含每组 n（n=8/9/10）与单位 ms；
4. `figure_audit.py` 好例 → 断言 exit 0（AUDIT PASS）；
5. 埋雷三连，各断言 exit 1 且命中违例码：
   - 删除 `fig1.svg` → `MISSING_FIGURE`；
   - `sed` 篡改 figures.md 中 `n=8` → `CAPTION_NUMBER_MISMATCH`；
   - 追加 `type: bar_se` 声明（三组 n 均 <30）→ `RULE_VIOLATION_BAR`；
6. 若本机有 matplotlib：再跑一次 `--force-png`，校验 PNG magic bytes 与 IHDR 尺寸后**删除 PNG（不入库）**。

全部断言通过，脚本最后打印 `RUN_EXAMPLE ALL CHECKS PASSED` 并 exit 0。

## 示意输出（example_output/ 内为真实跑出的文本产物）

- `result.json`：9 契约字段齐全，主检验 Kruskal-Wallis（treatB 右偏触发非参路线）H(2)=14.36, p=0.0008；
- `figures.md`：fig1 箱线+抖动散点（n<10 强制全点）、fig2 ECDF；图注含每组 n/均值/SD、检验方法、p、数据区间；
- `fig1.svg` / `fig2.svg`：纯 Python 手写 SVG（文本格式，允许入库）；
- `audit_pass.log`：`AUDIT PASS`。
