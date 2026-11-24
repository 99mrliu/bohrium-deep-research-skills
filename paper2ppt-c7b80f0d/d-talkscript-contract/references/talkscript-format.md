# talkscript-format.md — 讲稿与节拍 schema、字数预算推导、过渡句写法

## 1. 从时长到字数预算

口播语速假设（可在 rehearse.py / notes_lint.py 用 --cpm/--wpm 覆盖）：

- 中文：240 字/分钟（CPM）
- 英文：150 词/分钟（WPM）
- 混排：CJK 字符按 CPM、拉丁词按 WPM 分别计时后相加

推导：`总字数预算 = 分钟数 × 语速`。10 分钟英文报告 ≈ 1500 词。
注意 beats.json 里每拍除了 `beat_text` 还有 `transition` 与 `if_asked`，这些也计入
口播时长（每拍约多 25–35 词，即 10–14 秒），写稿时要预留。
`est_sec` 应取 `(beat_text 词数 + 过渡/备询词数) / 语速 × 60`，与文本估算偏差 >30%
会被 beat_cut 记 warning。

## 2. beats.json schema

```json
{
  "meta": {"case_id": "...", "minutes": 10, "max_slides": 8, "language": "en"},
  "beats": [
    {
      "id": "b3-methods",              // 必填建议：稳定标识
      "role": "methods",               // opening/background/methods/results/limitations/conclusion...
      "title": "页标题（缺省取 claim 前 60 字符）",
      "claim": "本拍唯一主张（必填）",
      "bullets": ["页面上 3 条以内的短句"],   // 缺省为 [claim]
      "beat_text": "本拍逐字讲稿（必填）",
      "transition": "引向下一拍的一句话（必填，非空）",
      "if_asked": "被问到时的补充（可选）",
      "evidence_refs": ["fig:Figure 1", "tab:Table 1", "anchor:7", "page:5"],  // 必填，非空
      "est_sec": 85                    // 必填，正数
    }
  ]
}
```

- `evidence_refs` 前缀：`fig:`/`tab:` 对应 evidence.json 的 caption 索引；`anchor:<id>`
  对应数值锚点；`page:<n>` 对应整页。beat_cut 会逐一校验存在性。
- 拍数 ≤ max-slides；全部 est_sec 之和须落在 `分钟数×60 的 ±10%` 内（beat_cut 的
  硬门禁，error 退出码 1）。

## 3. 拍的划分原则

- 一拍 = 一个口头主张（claim），对应论文的一个证据单元（一张图 / 一张表 / 一组锚点）。
- 顺序按口头叙事，不必照搬论文章节序；常见映射：abstract→opening、intro→background、
  methods→1–2 拍、每个主结果 1 拍、limitations 独立 1 拍、conclusion 1 拍。
- limitations 必须独立成拍并引用论文原文措辞，不允许并入 conclusion 稀释。

## 4. 过渡句写法

过渡句是"口头路标"，须满足：(a) 承上或启下；(b) 不出现在页面 bullets 里（否则
Jaccard 门禁受害）；(c) 一句话以内。可用句式：

- 承接："Next, let us look at how ..." / "Moving on, ..." / "接下来我们看……"
- 转折："However, a careful talk must also carry the caveats, ..."
- 收束："Finally, let me wrap up with ..." / "In summary, ..."

`if_asked`（备询）写法：以 "If asked ..." 开头，给出答案要点并指回论文页码，
例如 "If asked about reproducibility: parameters live in Table 1, page 2."。

## 5. 页面文字 vs 讲稿的分工

- 页面（title + bullets + footer）：电报式短句，≤6 条，供听众扫读；footer 小字放
  `Figure 1 (p.3); 0.42 W/(m·K) (p.4)` 这样的引用。
- 备注（= 讲稿）：完整口语句，含过渡与备询；允许出现页面关键词，但整体 token
  Jaccard 必须 ≤0.5（notes_lint 门禁）。经验：bullets 写名词短语、讲稿写完整句，
  自然落在 0.05–0.15。
