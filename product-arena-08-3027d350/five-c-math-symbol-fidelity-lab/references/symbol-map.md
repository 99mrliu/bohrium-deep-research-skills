# Symbol / ZapfDingbats → Unicode 映射与信任判据

## 1. 判据:何时信任抽取结果,何时按字体名推断

PDF 字符到 Unicode 的解码有多条路径,可信度不同:

| 情形 | 判据 | 处置 |
|---|---|---|
| 字体含 ToUnicode CMap | 抽取器(pymupdf/poppler)按 CMap 解码,输出非 ASCII 且非 U+FFFD | **信任**,计入 `trusted_decoded` |
| Base-14 标准字体(Symbol/ZapfDingbats)无 ToUnicode | 抽取器按内置编码表解码,输出已是希腊字母/符号 | **信任**,但保留 font 名在 verbatim 旁证 |
| Symbol 字体,抽取结果仍为 ASCII 原始码位(如 `a` 而非 `α`) | 该 PDF 缺 ToUnicode 且编码信息丢失,字节漏出 | **按字体名推断**:查 Adobe Symbol 编码映射表,计 replacement |
| ZapfDingbats 字体,码位在保守子集内 | 见 §3 | 映射,计 replacement |
| ZapfDingbats 字体,码位不在保守子集 | dingbat 字形无可靠语义对应 | **进 unmapped 台账,绝不猜** |
| 任何字体输出 U+FFFD / 无码位 / 非 BMP(>U+FFFF) | 解码失败或异常 | **进 unmapped 台账**,linear 用 `⟦U+XXXX⟧` 占位 |

核心原则:**verbatim 永远保留抽取器给出的原始字符**;映射只发生在 linear 字段,
且每一次替换都计入 fidelity_report 的 `replacements` / `replacement_detail`。

## 2. Adobe Symbol 编码映射表(脚本内嵌核心表)

键为内容流字节码位(十六进制),值为 Unicode 字符。`scripts/linearize_math.py`
中的 `SYMBOL_MAP` 即下表(共 149 条,与代码一致)。

### 低位区 0x20–0x7E

| 码位 | 字符 | 码位 | 字符 | 码位 | 字符 | 码位 | 字符 |
|---|---|---|---|---|---|---|---|
| 20 | (空格) | 28 | ( | 30–39 | 0–9 | 38 | 8 |
| 21 | ! | 29 | ) | 3A | : | 39 | 9 |
| 22 | ∀ | 2A | ∗ | 3B | ; | 3C | < |
| 23 | # | 2B | + | 3D | = | 3E | > |
| 24 | ∃ | 2C | , | 3F | ? | 40 | ≅ |
| 25 | % | 2D | − | | | | |
| 26 | & | 2E | . | | | | |
| 27 | ∍ | 2F | / | | | | |

大写希腊字母(0x41–0x5A,按拉丁字母顺序对应):

| 码位 | 字符 | 码位 | 字符 | 码位 | 字符 |
|---|---|---|---|---|---|
| 41 | Α Alpha | 4E | Ν Nu | 56 | ς sigma1(词尾) |
| 42 | Β Beta | 4F | Ο Omicron | 57 | Ω Omega |
| 43 | Χ Chi | 50 | Π Pi | 58 | Ξ Xi |
| 44 | Δ Delta | 51 | Θ Theta | 59 | Ψ Psi |
| 45 | Ε Epsilon | 52 | Ρ Rho | 5A | Ζ Zeta |
| 46 | Φ Phi | 53 | Σ Sigma | | |
| 47 | Γ Gamma | 54 | Τ Tau | | |
| 48 | Η Eta | 55 | Υ Upsilon | | |
| 49 | Ι Iota | | | | |
| 4A | ϑ theta1(花体) | | | | |
| 4B | Κ Kappa | | | | |
| 4C | Λ Lambda | | | | |
| 4D | Μ Mu | | | | |

小写希腊字母(0x61–0x7A):

| 码位 | 字符 | 码位 | 字符 | 码位 | 字符 |
|---|---|---|---|---|---|
| 61 | α alpha | 6E | ν nu | 76 | ϖ omega1(花体 pi) |
| 62 | β beta | 6F | ο omicron | 77 | ω omega |
| 63 | χ chi | 70 | π pi | 78 | ξ xi |
| 64 | δ delta | 71 | θ theta | 79 | ψ psi |
| 65 | ε epsilon | 72 | ρ rho | 7A | ζ zeta |
| 66 | φ phi | 73 | σ sigma | | |
| 67 | γ gamma | 74 | τ tau | | |
| 68 | η eta | 75 | υ upsilon | | |
| 69 | ι iota | | | | |
| 6A | ϕ phi1(花体) | | | | |
| 6B | κ kappa | | | | |
| 6C | λ lambda | | | | |
| 6D | μ mu | | | | |

其余低位符号:5B `[`、5C `∴`、5D `]`、5E `⊥`、5F `_`、60 `‾`、7B `{`、7C `|`、7D `}`、7E `∼`。

### 常用高位码位(脚本内嵌)

| 码位 | 字符 | 码位 | 字符 | 码位 | 字符 |
|---|---|---|---|---|---|
| A2 | ′ | B8 | ÷ | CB | ⊄ |
| A3 | ≤ | B9 | ≠ | CC | ⊂ |
| A5 | ∞ | BA | ≡ | CD | ⊆ |
| AB | ↔ | BB | ≈ | CE | ∈ |
| AC | ← | BC | … | CF | ∉ |
| AD | ↑ | C0 | ℵ | D0 | ∠ |
| AE | → | C1 | ℑ | D1 | ∇ |
| AF | ↓ | C2 | ℜ | D5 | ∏ |
| B0 | ° | C3 | ℘ | D6 | √ |
| B1 | ± | C4 | ⊗ | D7 | ⋅ |
| B2 | ″ | C5 | ⊕ | D8 | ¬ |
| B3 | ≥ | C6 | ∅ | D9 | ∧ |
| B4 | × | C7 | ∩ | DA | ∨ |
| B5 | ∝ | C8 | ∪ | DB | ⇔ |
| B6 | ∂ | C9 | ⊃ | DC | ⇐ |
| B7 | • | CA | ⊇ | DD | ⇑ |
| | | | | DE | ⇒ |
| | | | | DF | ⇓ |
| | | | | E0 | ◊ |
| | | | | E1 | ⟨ |
| | | | | E5 | ∑ |
| | | | | F1 | ⟩ |

完整官方表见 Adobe《Symbol Encoding》/ PostScript Language Reference 附录;
本表覆盖科研公式常见码位。未列入码位一律进 unmapped 台账,不外推。

## 3. ZapfDingbats 保守子集

dingbat 字形大多无稳定语义对应,脚本只内嵌极少数高置信映射
(`ZAPF_COMMON`,共 3 条):

| 码位 | 字符 | 说明 |
|---|---|---|
| 25 | ☞ | 指向手 |
| 6C | ● | 黑圆(常见列表符号) |
| 6E | ■ | 黑方块(常见列表符号) |

**其余所有码位 → unmapped 台账**。完整编码向量见 Adobe/ITC ZapfDingbats
Encoding 规范;因语义不确定性,本 Skill 不内嵌全表、不猜测。

## 4. 台账条目格式

每个 unmapped 条目含:`page`(页码)、`bbox`(坐标)、`font`(字体名)、
`raw_codepoint`(原始码位,U+XXXX)、`extracted_char`(抽取器给出的字符)、
`reason`、`zone_id`(所属公式区,区外为 null)、`context`。
