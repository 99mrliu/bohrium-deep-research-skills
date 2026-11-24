# 任务说明（合成示例 / synthetic, illustrative）

围绕研究问题「运动干预能否降低 65 岁以上老年人的跌倒风险？」完成一次简化的
系统性文献综述流程，重点演示**论断回链审计**：

1. 对 `sources/` 下的 3 篇合成研究全文与 `records.json` 题录建 span 索引
   （`index_sources.py`）。
2. 把筛选与提取阶段得到的证据片段登记为 `extractions.jsonl`（带 span 定位）。
3. **先写 `claims.jsonl` 再写综述正文**：每条论断给出 strength
   （fact/inference/uncertain）与 evidence（record_id + span_id + quote）。
4. 运行 `audit_claims.py` 核验每条 quote 都是指定 span 的 verbatim 子串，
   且强度措辞与证据匹配；全绿（exit 0）后才允许组装正文。
5. 运行 `build_matrix.py` 生成论断 × 文献覆盖矩阵与冲突证据矩阵。

预期结果：正例 6 条论断全部通过（exit 0）；`negative/` 下四个埋雷文件
分别触发 C2 / C3 / C5 / C4，均 exit 3。

本示例全部数据均为虚构，仅演示接口与流程，不得冒充正式案例结果。
