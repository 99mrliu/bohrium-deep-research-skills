# 任务说明（合成示例 / SYNTHETIC，非正式案例）

> 本文件是 source-veracity-gate 自带的**合成示例**任务说明，语料与文献全部虚构，
> 仅用于演示 Skill 的审计与门控能力，不冒充正式测评案例。

从种子论文 `10.0000/synth.001`（"A Synthetic Gradient Method for Citation Flow"）
出发：

1. 先对 `corpus/` 下的全部语料文件做来源审计：登记每个文件的 sha1、格式判定、
   解析记录数与失败原因；注意其中有一个**故意损坏**的 JSON 文件，以及一对
   **同 DOI 不同标题**的冲突记录。
2. 再做 1–2 层引文扩展：沿 references 向后找被引出处，沿反向索引恢复的前向边
   找施引后续；种子还引用了一篇语料内不存在的文献（`10.0000/synth.999`），
   应保留为 stub 而不得补造元数据。
3. 交付 `result.json`：逐字段镜像 `case.json` 的 `output_contract`，每条候选与
   每条边都必须带 `{file, pointer}` 来源定位；`output_contract` 中的
   `novelty_statement` 字段在本案例中未定义语义，应给诚实空值并写入
   `uncertainty`。
