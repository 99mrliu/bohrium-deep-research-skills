# 最小示例（合成，非正式测试案例结果）

## 输入

`examples/input/`：`corpus_note.md` 描述 3 篇虚构文献（全部为演示编造）；
`docket_good.jsonl`（合法卷宗：G1 含 1 支持 + 1 反证 + 对抗检索记录，
G2 含 1 间接支持 + found=false 的对抗检索记录）；`docket_bad.jsonl`
（故意缺全部对抗检索记录）。

## 运行

```bash
bash examples/run_example.sh
```

## 实跑结果（示例产物，标注为合成示例）

1. `lint docket_good.jsonl`：**exit 0**；
2. `lint docket_bad.jsonl`：**exit 1**，两组均被判"缺对抗检索记录
   （不许只登记支持性证据）"（`output/lint_bad.json`）；
3. `adjudicate docket_good.jsonl`：`output/tribunal/` 中——
   - **G1 → support，决定准则=方法严谨度**：两篇直接实验结论相反，
     直接性、证据类型持平，high 严谨度胜过 medium；注意反证更新（2025），
     但时效准则排在最后，不能抵消严谨度差距——这正是显式准则优先级的意义；
   - **G2 → unchallenged**：对抗检索未找到反证，综述中必须标注
     "未经对抗检验"，不许写成"已被证实"。

关键观察点：程序缺失（没找反证）会被 lint 确定性拒绝；程序完整时，
裁决由准则机械作出，unresolved/unchallenged 都有强制引用口径。
