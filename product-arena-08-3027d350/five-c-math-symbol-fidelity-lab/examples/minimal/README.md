# 最小示例(合成示例,非正式案例、非真实论文)

本示例演示 math-symbol-fidelity-lab 的完整四步管线。输入 PDF 由
`inputs/make_sample.py`(**纯标准库**)合成,全部产物(`outputs/`)为脚本真实运行的
落盘结果,非手写。

## 合成输入设计(inputs/sample_math.pdf,2 页,ASCII-clean)

| 元素 | 构造方式 | 考察点 |
|---|---|---|
| 正文 | Helvetica(/F1)12pt | 不应被判为公式区 |
| α + β = γ | /Symbol 标准字体写内容流字节 `a + b = g` | 希腊字母信号 + 编号配对 (1) |
| E_i = x^2 + χψ | /F1 混排:7pt "i" 基线降 5pt(下标)、7pt "2" 基线升 6pt(上标);/F2 写 `cy` → χψ | 上下标重建 + 编号配对 (2) |
| Marker: ❦ | /ZapfDingbats 写生僻码位 0xA6(八进制 `\246`) | **真实触发 unmapped 台账**(该码位不在保守映射子集) |
| Sum: α + β | 行内数学,无编号 | 公式区但 number=null |
| Σ φ(ξ) = Ω | 第 2 页 /F2 写 `S f(x) = W` | 跨页 + 编号配对 (3) |

## 复现命令

```bash
cd examples/minimal
python3 inputs/make_sample.py    # 重新生成 inputs/sample_math.pdf
S=../../scripts; W=/tmp/msf-work; mkdir -p $W
python3 $S/extract_glyphs.py inputs/sample_math.pdf --out $W/glyphs.jsonl --report $W/extract_report.json
python3 $S/detect_math_zones.py $W/glyphs.jsonl --out $W/math_zones.json
python3 $S/linearize_math.py $W/glyphs.jsonl $W/math_zones.json --out $W/equations.json \
    --report $W/fidelity_report.json --extract-report $W/extract_report.json
python3 $S/make_result.py --case inputs/case.json --glyphs $W/glyphs.jsonl \
    --zones $W/math_zones.json --equations $W/equations.json \
    --fidelity $W/fidelity_report.json --extract-report $W/extract_report.json \
    --out $W/result.json
diff $W/equations.json outputs/equations.json   # 应与入库产物一致(除时间戳)
```

预期退出码:第 1、2 步 0;第 3、4 步 **2(诚实 partial:存在 1 个未映射符号)**。

## 目检结论(实际逐项核对过)

1. **char 级数据验证**:pymupdf rawdict 每字符带 `c/font/size/bbox/origin`——已确认
   (如 'E' size=12 origin.y=182;上标 '2' size=7 origin.y=176)。
2. **verbatim 对照**:pdftotext 抽出文本与 equations.json 的 verbatim 逐条一致
   (`α + β = γ`、`Ei = x2 + χψ`、`Σ φ(ξ) = Ω`);pdftotext 将编号与 dingbat 拆成
   散行,正说明 char 级引擎的必要性。
3. **线性化正确性**:
   - eq-002 `linear = "E_{i} = x^{2} + χψ"` ✓(上/下标方向与括号分组均正确);
   - eq-001/004 希腊字母与数学符号原样通过,`\Sigma \phi(\xi) = \Omega` 字符级一致 ✓。
4. **编号配对**:(1)(2)(3) 全部从公式体剥离进 `number` 字段;行内 `f(x)` 的括号
   未被误判为编号(60% 行跨度右端约束生效)✓。
5. **unmapped 台账真实触发**:ZapfDingbats 0xA6(抽取器解出 'k' U+006B)进台账,
   含页码 1、bbox [125.0, 211.79, 134.12, 223.79]、字体名、原始码位、原因;
   `context="outside-math-zone"`(该字符在正文行,全局特殊字体扫描捕获)✓。
6. **状态流转**:fidelity_report `status=partial`,result.json `status=partial`
   且 `uncertainty` 写明"未映射符号 1 个"——诚实告警,未伪造 success ✓。

## 降级路径自测(另测,未入库)

- `--engine pdftotext` 强制词级降级:extract 退出码 2,两页 mode=word、zones 标
  partial,上下标判定跳过("E i = x 2" 保持原序),线性化整体 partial ✓。
- `map_char` 单元自测 5/5:Symbol 原始字节 'a'→α(计 replacement);已解码 'α'→信任;
  ZapfDingbats 0x6E→■;U+FFFD→台账;非 BMP→台账 ✓。
