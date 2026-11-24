# examples / 合成示例（SYNTHETIC EXAMPLE）

本目录全部输入输出为 **合成示例 / SYNTHETIC EXAMPLE**：虚构情景数据，用于演示
decision-forge-qc 的用法与质量门行为，不是正式案例结果，不得冒充评测产物。

## 文件

| 文件 | 说明 |
|------|------|
| `case.example.json` | 合成 case：含 5 键 `output_contract`（selected_plan / decision_log / confidence_level / sensitivity_summary / key_risks）与一条硬约束（4 周期限） |
| `package_good.json` | 正例决策包：3 方案（P_A/P_B/P_C），七类字段完整、淘汰证据齐全、确认项全部 confirmed、result_skeleton 键完整 |
| `package_bad.json` | booby-trap 负例：故意埋 4 个缺陷（见下），预期 exit 3 精确拦截 |
| `outputs/` | 下列命令**真实跑出**的产物（已目检） |

负例 4 个缺陷：① P_B 的 controls 组为空（`FIELD_GROUP_EMPTY`）；② 对 P_C 的
elimination 缺 evidence_refs（`ELIMINATION_EVIDENCE_MISSING`）；③ rationale 把
pending 确认项 CONF-EQP-01 写成已确认（`SELECTION_CITES_PENDING`）；④
result_skeleton 漏 output_contract 键 `key_risks`（`CONTRACT_KEY_MISSING`）。

## 命令序列（从 bundle 根目录执行）

```bash
cd <bundle根目录>   # 即 e-decision-forge-qc/

# 合成示例标注：嵌入每个 JSON 产物顶层 note 键与 Markdown 产物首行引用块
NOTE="合成示例 / SYNTHETIC EXAMPLE：本报告由虚构输入生成，仅演示接口与流程，非正式案例结果。"

# 1. 质量门：正例 → 预期 exit 0
python3 scripts/quality_gate.py --package examples/package_good.json \
    --case examples/case.example.json --outdir examples/outputs --note "$NOTE"
#    （本目录把产物重命名为 gate_report_good.{json,md} 以与负例区分）

# 2. 质量门：负例 → 预期 exit 3，stdout 恰好列出上述 4 个缺陷（产物仍写出，重命名为 gate_report_bad.{json,md}）
python3 scripts/quality_gate.py --package examples/package_bad.json \
    --case examples/case.example.json --outdir examples/outputs --note "$NOTE"

# 3. 敏感性分析 → 预期 exit 0，verdict=sensitive，2 个触发扰动
python3 scripts/sensitivity.py --package examples/package_good.json \
    --outdir examples/outputs --note "$NOTE"

# 4. 渲染报告 → 预期 exit 0，生成 report.html + report.md
python3 scripts/report_render.py --package examples/package_good.json \
    --sensitivity examples/outputs/sensitivity.json --outdir examples/outputs

# 5. 全流程自查 → 预期 exit 0（12/12 断言通过）
python3 scripts/selfcheck.py
```

## 在浏览器目检 report.html

macOS：`open examples/outputs/report.html`；或把该文件拖入任意浏览器。
目检要点：顶部黄色「合成示例 / SYNTHETIC EXAMPLE」横幅；第 1 节选定方案 P_A
与 final 状态；第 2 节确认项 confirmed/pending 分区；第 3 节七张子表（七类字段
× 3 方案）；第 4 节决策日志（P_C 按 hard_threshold_timeline 淘汰，证据
C-RES-1/C-RES-2）；第 5 节权重与加权总分表；第 6 节敏感性情景表（
reliability_down 与 equal_weights 两行标红「是」）与翻转阈值表；页脚固定标注
生成方式与案例 id。报告为自包含 HTML（内联 CSS、无外部依赖、无 JS），双击即
可打开，无需网络。

## 敏感性手算验算（与 outputs/sensitivity.json 对账）

权重（和为 1，无需归一化）：reliability 0.4, cost 0.2, duration 0.2, safety 0.2。
维度分：

| 方案 | reliability | cost | duration | safety | 基线加权总分 |
|------|------------|------|----------|--------|-------------|
| P_A | 5 | 2 | 4 | 4 | 5×.4+2×.2+4×.2+4×.2 = **4.0** |
| P_B | 3 | 5 | 3 | 3 | 1.2+1.0+0.6+0.6 = **3.4** |
| P_C | 2 | 4 | 5 | 5 | 0.8+0.8+1.0+1.0 = **3.6** |

基线排名 P_A(4.0) > P_C(3.6) > P_B(3.4)。

**扰动情景**（被扰权重 ×0.5/×1.5，其余按比例归一）：

- reliability ↓ 至 0.2，其余各 ×(0.8/0.6)=4/3 → 各 0.266667：
  P_A = 1.0 + 10×0.266667 = 3.666667；P_B = 0.6 + 11×0.266667 = 3.533333；
  P_C = 0.4 + 14×0.266667 = **4.133333 ⇒ 翻转 A→C** ✔
- 等权重（各 0.25）：P_A = 15/4 = 3.75；P_B = 14/4 = 3.5；
  P_C = 16/4 = **4.0 ⇒ 翻转 A→C** ✔
- 其余 7 个情景（cost↑/↓、duration↑/↓、safety↑/↓、reliability↑）P_A 均保持
  第一，例如 cost↑ 至 0.3、其余 ×0.875（rel .35, dur .175, saf .175）：
  P_A = 1.75+0.6+0.7+0.7 = 3.75 > P_C 3.65 > P_B 3.6，不翻转 ✔

⇒ verdict = **sensitive**，触发扰动 = {reliability_down, equal_weights}。

**翻转阈值解析解**（单维权重 t 变化、其余保持相对比例时，各方案总分关于 t
线性，求 P_A 与追赶者平分点）：

- reliability：P_A(t) = 5t + 2.0×(1−t)/0.6，P_C(t) = 2t + 2.8×(1−t)/0.6，
  联立得 t = 4/13 ≈ **0.307692**（下调方向，翻转为 P_C）✔
- cost：P_A(t) = 2t + 3.6×(1−t)/0.8，P_B(t) = 5t + 2.4×(1−t)/0.8，
  联立得 t = 1/3 ≈ **0.333333**（上调方向，翻转为 P_B）✔
  （cost↑ 实测只到 0.30 < 1/3，故该情景不翻转，与上条一致）
- duration / safety：P_A 在该两维的分数恰等于其非该维均值的缩放值，总分恒为
  4.0；P_C 追上需 t = 3/7 ≈ **0.428571**（上调方向，翻转为 P_C）✔

以上数值与 `outputs/sensitivity.json` 的 `thresholds`、`verdict.triggers` 逐项
一致；`selfcheck.py` 内置同样的手算期望值做回归断言。
