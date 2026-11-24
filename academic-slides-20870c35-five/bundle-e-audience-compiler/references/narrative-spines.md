# narrative-spines.md — 叙事角色词表与三种场合的脊柱模板

本文件定义 `scripts/storyboard_gate.py` S4/S6 的语义，并给出 review /
defense / group_meeting 三种汇报场合的推荐脊柱（spine）。

## 1. 受控角色词表（S4 词表检查）

| role | 语义 | 是否背景页（S5） |
|---|---|---|
| hook | 开场钩子：一个数字、一个矛盾、一个决策场景 | 是 |
| problem | 问题定义：谁在为什么付出什么代价 | 是 |
| gap | 空白：文献/现有方法缺什么 | 是 |
| approach | 进路：把问题重铸成什么可解形式 | 否 |
| method | 方法：怎么做（模型、实验设计、协议） | 否 |
| result | 结果：一条带证据的主张 | 否（S6 强制 exhibit） |
| comparison | 对照：与 baseline/现有技术的量化比较 | 否（S6 强制 exhibit） |
| limitation | 局限：主张的边界，诚实声明 | 否 |
| conclusion | 结论：希望听众记住并据此行动的一句话 | 否 |
| outlook | 展望/请求：下一步、资源、时间表 | 否 |
| backup | 备用页：问答时按需翻，不计入主故事线 | 不计入 |

规则：一页一个角色；backup 页必须 `backup:true` 且角色用 `backup`。

## 2. 主干顺序约束（所有场合通用）

首次出现序号（仅主故事线，0 基）须满足：

    problem < approach < result < conclusion

含义：进路不能在问题之前抛，结果不能在进路之前给，结论不能在首个结果之前下。
角色缺席则相应约束自动失效（但 review 场合 conclusion 不可缺席，见 §3）。

## 3. 三种场合的脊柱模板

### review（评审/基金/开题）：结论先行

评委的决策在前几分钟形成。脊柱：

    S1 hook → S2 problem → S3 approach → S4 result(头条) → S5 conclusion
    → S6 method → S7 result(细节) → S8 comparison → S9 limitation → S10 outlook
    （+ backup 页若干）

- 硬门控：首个 conclusion 页 0 基序号 ≤ ceil(n_main/3)。
- conclusion 之后放 method/细节 result/comparison 是**故意的**：评委已经知道
  你要什么，后面的每一页都是在为已陈述的结论补证据。
- 注意主干顺序仍须成立：在 conclusion 之前至少出现过一次 problem、approach、
  result（头条结果页就是为同时满足"结论先行"与"result<conclusion"而设）。

### defense（学位答辩）：边界先于结论

答辩委员会寻找"结论大于证据"的破绽。脊柱：

    hook → problem → gap → approach → method → result(×2–3)
    → comparison → limitation → conclusion → outlook

- 硬门控：必须存在 limitation 页，且其首次出现早于首个 conclusion 页。
- limitation 不是示弱，是收缴对方的攻击面：自己先讲的边界，委员追问时
  你已有口径（配合问答备用页）。
- 创新点建议落在 approach/method 页的 message 里，逐页可指认。

### group_meeting（组会/例会）：方法与进度为主

听众是同组同行，目标是获得可执行反馈。脊柱：

    problem(短) → approach → method(×2) → result(进度性) → limitation → outlook(风险与求助)

- 不设 conclusion 位置硬门控；主干顺序仍适用。
- method 与"进度/风险"是主体；背景压到带下限；outlook 页写清下一步与
  需要的资源/讨论点。

## 4. 每页五要素（storyboard 条目规范）

每页必须写全，缺一不可：

1. **message**：恰好一个主张的单句（S2：终止符 ≤2、无列表标记）。写不出
   单句说明该页装了两个主张——拆页。
2. **role**：§1 词表之一。
3. **notes**：讲稿，按 talk_spec 的每页时间预算定量落笔
   （`per_slide_seconds × wpm / 60` 词；CJK 按字），S3 据此计时。
4. **transition**：到下一页的一句转场（"既然方法可行，代价是什么？"），
   保证起承转合而非页面罗列；末页可为 null。
5. **exhibits**：result/comparison 页必须 ≥1 个定位器
   `{file, page, exhibit}`（S6），指到源材料的具体图/表，例如
   `{"file": "paper.pdf", "page": 5, "exhibit": "Figure 2"}`。
   定位器在 Phase 1 的源索引里必须真实存在——S6 只查绑定存在性，
   绑定内容的真实性由源锚定流程保证。

## 5. 常见失败模式（本 bundle 针对的反模式）

- **页数与时长脱节**：12 分钟塞 20 页，每页 36 秒只能念标题。S1+S3 拦。
- **按论文目录逐节搬运**：Introduction 三页、Related Work 两页……背景
  比例冲到 50%。S5 拦。
- **结论压尾**：评审听到第 11 页才知道你要什么。S4 场合规则拦。
- **结果页裸奔**：口报数字却不指到图/表，评委无法核对。S6 拦。
- **一页多主张**：message 写成三个句子加列表。S2 拦。
