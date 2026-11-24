# 复跑确定性与产物指纹

## 三个层次

1. **脚本确定性**：本技能全部脚本同输入同输出（台账时间戳用 --timestamp
   固定时完全逐字节一致；不固定时仅时间戳字段不同）；
2. **判定确定性**：同一批题录、同一版标准，两次运行的 decisions 应当
   集合一致、标签一致、理由码一致——rerun_diff.py 以此判定
   deterministic，evidence_snippet 的措辞差异单列人工过目；
3. **交付完整性**：manifest.py 固化产物 sha256；复核者 verify 全同
   即证明"你看到的就是我跑出来的"。

## 非确定性的处置流程

rerun_diff 报 NONDETERMINISTIC（exit 3）时按序排查：

1. 两次运行的输入是否一致（对输入也做 manifest）；
2. 判定环节是否有人工介入未留痕（台账 operator 字段应对得上）；
3. 模型判定是否未固定标准版本（标准漂移的典型信号）；
4. label_flips 的记录逐条回看：哪一次符合标准原文，把理由码写进
   更正记录，禁止"取多数"和稀泥。

查明原因并修正后重跑到 DETERMINISTIC 才可交付；无法消除时，
result.json status=partial，把 flips 清单放入 uncertainty 并说明原因。

## 局限声明

- rerun_diff 是集合语义对比，不验证"判定是否正确"，只验证"是否一致"；
- manifest 证明产物未被改动，不证明产物内容正确；
- 两者结合给出的是**可复核性证据**，正确性仍依赖判定环节本身的证据锚定。
