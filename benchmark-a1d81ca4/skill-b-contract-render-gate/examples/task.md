# 工单（合成示例 SYNTHETIC EXAMPLE）

类型：T2 benchmark-DRAFT 出题工单（task.md 含"出题/题卡/DRAFT"触发词）。

请阅读本目录下的 `source_excerpt.txt`（虚构的电池/材料段落与表格），
**出题**：从中草拟 **2 道** 题卡（注：本示例为节省体量只演示 2 道，
正式工单要求 **4 道**）。

每道题卡必须包含七个要素：
任务、材料范围、参考答案、评分规则、证据锚点（指向 source_excerpt.txt
的真实行号，格式 `source_excerpt.txt:L<行号>`）、难度、授权。

agent 的产出写入工作文件（items.json 提供 item_bank / answer_summary /
status_note，evidence_map.json 提供证据锚点映射），随后由本技能完成
契约化填充、渲染预览与门禁交付。
