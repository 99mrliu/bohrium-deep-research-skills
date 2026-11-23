# 门禁规则（evidence_gate.py）

门禁是**渲染前置条件**：`verdict=passed`（退出码 0）之前不得渲染、不得交付"完成"。

## 运行

```bash
python3 scripts/evidence_gate.py /app/work/ledger.json \
    --sources-dir /app/work/sources --report /app/work/gate_report.json
```

退出码：`0` 全部 verified/waived；`1` 有失败项；`2` 参数/IO 错误（仍尽量写报告）。

## 判定（verdict）

| verdict | 含义 | 是否阻断 |
|---|---|---|
| `verified` | quote 归一化后**精确**出现于 source.file 中 | 否 |
| `unverified` | 源文件存在但匹配失败；附 `near_miss` 提示 | **是** |
| `missing-source-file` | source.file 在 sources 目录中不存在（含 `../` 越界） | **是** |
| `invalid` | 缺 id/kind/label/source.file/source.quote，或豁免无理由 | **是** |
| `waived` | 显式豁免（见下） | 否 |

## 归一化（对 quote 与源文本同样施加，然后做子串匹配）

1. Unicode NFKC：全角字符→半角、兼容字符归一（如 `（`→`(`、全角数字→半角）。
2. 弯引号/破折号映射：`“ ”‘ ’`→`" '`、`– — −`→`-`、`…`→`...`；删除软连字符。
3. 空白折叠：任意连续空白（含换行）→ 单个空格，首尾去除。→ **quote 跨行也能命中**。
4. CJK 间空格剔除：两个 CJK 字符之间的单个空格删除。
   （`pdftotext` 常在中文排版处插入换行/空格，此规则吸收该噪声。）

**不做的归一化**（避免放水）：不改大小写、不统一简繁、不改写数字与单位、不做词形还原。
quote 里的每个事实字符都必须真在原文里。

## 近失提示（near_miss）

`unverified` 时，报告对源文本逐行/逐句计算 `difflib.SequenceMatcher` 相似度，
返回前 3 个 ≥0.45 的候选：`{"similarity": 0.944, "candidate": "..."}`。
用法：把 quote 替换为 candidate 中的**原文**（不是把 candidate 改成你的 quote）。
相似度再高也不是证据——只有 `verified` 是证据。

## 豁免政策（waiver）

- 仅允许用于**非事实性**内容：图注、绘图约定说明（"箭头表示先后顺序"）、标题性元素等。
- 写法：元素加 `"waived": true` + `"waiver_reason": "<理由>"`。缺理由判 `invalid`。
- 豁免元素在图上以琥珀色虚线描边 + `[waived]` 角标呈现；图例与 gate_report.json
  如实统计豁免数；result.json 的 sources/uncertainties 中必须再次列出豁免及其理由。
- **红线**：事实性陈述（装置、参数、步骤、数据、流向）不得豁免。发现即视为造假未遂，
  应删除或补证据。豁免是披露机制，不是逃生门。

## 工作实例

设源文件 `methods_excerpt.txt` 含行：
`三角瓶置于恒温摇床，在 37 °C、180 rpm 条件下酶解 4 h。`

| # | quote | 结果 | 说明 |
|---|---|---|---|
| 1 | `三角瓶置于恒温摇床，在 37 °C、180 rpm 条件下酶解 4 h。` | ✅ verified | 逐字复制 |
| 2 | `三角瓶置于恒温摇床，\n在 37 °C、180 rpm 条件下酶解 4 h。`（PDF 跨行抽取） | ✅ verified | 空白折叠后命中 |
| 3 | `三角瓶置于恒温摇床，在 ３７ °C 酶解 ４ h。`（全角数字） | ✅ verified | NFKC 归一后命中 |
| 4 | `三角瓶置于恒温摇床，在 37 °C、200 rpm 条件下酶解 4 h。` | ❌ unverified | near_miss ≈0.94 指向原行；改回 `180 rpm` |
| 5 | `酶解产物经喷雾干燥得到粉末。` | ❌ unverified | 源文本无此事实 → 删除元素或另找证据 |
| 6 | note 元素 `"waived": true, "waiver_reason": "绘图约定说明，无对应原文"` | ⚠️ waived | 如实披露，不阻断 |
| 7 | 同上但无 `waiver_reason` | ❌ invalid | 补理由或走门禁 |

## 常见失败模式与对策

| 症状 | 原因 | 对策 |
|---|---|---|
| 大量 unverified | quote 凭记忆复述而非复制 | 用编辑器/脚本从抽取文本中复制粘贴，杜绝手打 |
| 个别 unverified，near_miss>0.9 | 笔误、标点差异 | 按 candidate 原文整体替换 quote |
| missing-source-file | file 写错/抽取文件名改了 | 核对 `--sources-dir` 下实际文件名 |
| 中文总是匹配不上 | 抽取文本乱码（PDF 编码问题） | 换 `pdftotext -layout` 重抽；乱码无法消除则声明 OCR/降级 |
| 想豁免事实性内容 | — | 不允许；删除该元素或收窄 label 到 quote 可支撑的范围 |
