# Style guides — five genres (语气 / 人称 / 禁忌 / 模板句式)

Each genre lists: voice & person norms, taboos, template sentence patterns, and
wrong → right pairs (✗ wrong / ✓ right / why). These guides back the edits an
agent makes after `register.py lint` flags a hit; always adjudicate in context
(see `register-taxonomy.md` for boundaries).

---

## 1. journal-abstract 期刊摘要

- **Voice**: impersonal, third person. Chinese: “本文/本研究” (not “我”, avoid
  “我们”). English: “this paper / this study / we (plural)”, never “I”.
- **Tense (EN)**: present for facts and conclusions, past for methods/results.
- **Taboos**: hype (breakthrough, cutting-edge, 填补空白), absolute claims,
  contractions, colloquial intensifiers, citations in the abstract (venue
  dependent), undefined abbreviations.
- **Templates**: “本文提出……，实验表明……” / “We propose …; experiments on
  … show that …”

| ✗ wrong | ✓ right | why |
|---|---|---|
| I really think our method is revolutionary. | The proposed method improves accuracy by 4.2 points on X. | first-person singular + intensifier + hype |
| We can't deny the results are pretty good. | The results do not support the null hypothesis (p < 0.01). | contraction + hedged boast |
| 我们搞了个新方法，效果挺好。 | 本文提出一种……方法，在三个基准上性能提升 12.5%。 | 口语词“搞/挺”；“我们”改“本文” |
| This cutting-edge approach will never fail. | The approach remained stable under all tested conditions. | hype + absolute |
| 该算法彻底解决了过拟合问题。 | 该算法在三个数据集上显著缓解了过拟合。 | 无证据绝对化 |

## 2. thesis 学位论文

- **Voice**: formal, signposted (“本章/第 3 章/本文”). Person: “本文/本研究”;
  “我们” is a warning, “我” forbidden outside the acknowledgements (致谢).
- **Taboos**: colloquial verbs (搞/弄), empty intensifiers, addressing the
  reader (“you/你”), promises instead of findings.
- **Templates**: “本章结构安排如下：……” / “如图 2 所示，……” /
  “本章小结：……”

| ✗ wrong | ✓ right | why |
|---|---|---|
| 我搞了很多实验来证明我的想法。 | 本文设计了系列对照实验，以验证第 3 章提出的假设。 | 人称 + 口语 |
| You can see from Figure 2 that the curve is really smooth. | As shown in Figure 2, the curve varies smoothly (std 0.03). | second person + intensifier |
| The results were pretty amazing. | The results exceeded the baseline by 12.5%. | vague praise → measured |
| Lots of researchers have looked at this. | 已有大量研究关注该问题 [3-5]。 | colloquial quantifier |
| 本章弄清了全部机理。 | 本章阐明了……的主导机理。 | 口语 + 绝对化 |

## 3. grant-proposal 基金申请书

- **Voice**: confident but **evidence-bound**. Person: “本项目/申请人（团队）/
  我们” are all acceptable; “我” is not. Future work uses “拟/计划”.
- **Taboos**: bare hype without evidence (“国际领先/填补空白” must be tied to
  literature or preliminary data — lint emits *warnings*, not violations, for
  this genre), absolute promises (“彻底解决/必将”), colloquialisms.
- **Templates**: “本项目拟解决……关键科学问题” / “前期结果表明……（已发表
  成果 [5]）” / “据我们所知，国内尚无系统研究（见立项依据 [2-4]）”

| ✗ wrong | ✓ right | why |
|---|---|---|
| 本项目将填补国内空白，达到国际领先。 | 据我们所知国内尚无系统研究 [2-4]；本项目拟形成自主方法。 | 宣传语须带可验证依据 |
| 我们搞了一套工艺，特别省钱。 | 申请人团队建立了一套……工艺，制备成本降低约 30%（前期工作，图 1）。 | 口语 → 量化 |
| 该技术必将彻底解决行业痛点。 | 该技术有望显著缓解……问题。 | 无证据绝对化承诺 |
| Everyone knows this is a breakthrough. | 前期结果已发表于 [5]，显示…… | hype → evidence |

## 4. review-response 审稿回复

- **Voice**: courteous, point-by-point. Every response block should contain
  “We thank the reviewer …” and “We have revised / added / clarified …”.
  Quote the comment verbatim, then the response, then the location of the
  change (page/line).
- **Taboos**: combative tone (“the reviewer is wrong”, “obviously”), bare
  claims without a manuscript pointer, hype, contractions.
- **Templates**: “We thank the reviewer for this insightful comment. We have
  revised Section 2.3 (page 4, lines 120-135) to …” / “We respectfully
  clarify …; the revised text now states …”

| ✗ wrong | ✓ right | why |
|---|---|---|
| The reviewer is wrong about the baseline. | We thank the reviewer for raising this point. The baseline follows [7]; we have clarified this on page 4. | combative → courteous + pointer |
| Obviously our method works. | We have added an ablation study (new Table 3) demonstrating the effect. | dismissive → evidence |
| We fixed it. | We have revised Section 2.3 to state the assumption explicitly. | vague → located revision |
| This doesn't matter for our paper. | We agree the point is peripheral; we have nevertheless added a short discussion (page 9). | contraction + dismissive |

## 5. en-abstract 英文摘要 (English abstract, e.g. of a thesis)

- **Voice**: no contractions, no informal intensifiers, no first-person
  singular; “this thesis/paper” or “we”. Concise: one idea per sentence.
- **Taboos**: “a lot of / lots of / get + participle / just / really / pretty”,
  hype, absolute claims, “I”.
- **Templates**: “This thesis investigates …” / “A … framework is proposed.” /
  “Experiments on three datasets show a 12.5% reduction in latency.”

| ✗ wrong | ✓ right | why |
|---|---|---|
| It doesn't need any labels and it's still very accurate. | The method requires no labels while maintaining high accuracy. | contractions |
| We got better results in a lot of tasks. | The method outperformed the baselines on 8 of 10 tasks. | get+PP + a lot of |
| I really believe this will change the field. | These findings suggest a promising direction for … | I + intensifier + hype |
| Our approach is cutting-edge and always works. | The approach achieved competitive accuracy on all tested benchmarks. | hype + absolute |
| There're lots of ways to solve this, but ours is just better. | Existing approaches …; the proposed method reduces error by 9%. | contractions + colloquial |
