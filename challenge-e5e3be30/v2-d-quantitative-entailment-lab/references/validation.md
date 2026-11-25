# 本地 SYNTHETIC 验证记录

本文件记录工程验证，不是官方 benchmark 得分、论文效果或实证结论。所有测试数值均为 **SYNTHETIC**。

## 独立计算断言

`selftest.py` 不调用实现来生成期望。固定期望来自独立 hand/direct-formula 计算：

- raw 70/100 与 60/120：p1=7/10、p0=1/2；percentage-point=20、relative=2/5=0.4、ratio=7/5=1.4。
- displayed 70% 与 60%：percentage-point=10、relative=(.7-.6)/.6=1/6。
- pooled=(70+60)/(100+120)=13/22。
- SE0=sqrt((13/22)*(9/22)*(1/100+1/120))=0.06657190234489459。
- z=0.2/SE0=3.0042704647952423。
- 双侧 p=erfc(|z|/sqrt(2))=0.002662185508945006。
- zc=1.959963984540054 的 Wilson 95% CI：
  - 70/100：[0.6041514536665332, 0.7810511470506724]；
  - 60/120：[0.41193870541108385, 0.5880612945889161]。
- 2500 ms ×1e-3=2.5 s。

测试断言这些数字以及 comparison 状态，而非只断言 truthy/nonzero。由于二进制浮点，20pp 可以表示成 19.999999999999996；测试用明确数值精度断言，运行时用 claim 的绝对/相对容差比较。

## 行为路径

自测还断言：所有 derived 有 formula/source ids 且 verdict=null；display/raw 冲突并列；source-reported p target 不自动 refute；稀疏 expected cells <5 给 warning；跨量纲单位失败；每种 observation quote 能在合成 paper 找到。

命令级测试覆盖：

- 端到端 paper/claims/observations/Agent verdict → report、SVG、result；动态 contract pass；四条 verdict 精确为 supported、partially_supported、insufficient_evidence、supported。
- 非法 n=0：`build_report.py` exit 1，stderr 指明 positive integer。
- 非法 confidence=1.0：exit 1，stderr 指明 strictly between 0 and 1。
- 显式缺失 observations：early contract-shaped result 已存在、status=partial、claim verdict=null、sources/change_records 保留，runner exit 1。
- list 字段契约产生 claims list；dict 类型契约产生以 claim id 为键的 claims dict，并被成功态审计正确计数；object status 的 state 同样参与契约检查。
- 即使 Agent verdict 完整，没有发现论文源时仍降级 partial，并在 uncertainty 披露。

`verify_bundle.py` 另检查最多50文件、单文件≤500KiB、总量≤2MiB、严格UTF-8文本、无 NUL、无 symlink、无 pyc/cache、无 README、无本机绝对路径、GITHUB_URL.txt 精确首行，以及 SKILL.md frontmatter 仅 name/description。

命令：

```sh
python3 scripts/selftest.py
python3 scripts/verify_bundle.py
```

测试并未覆盖真实 PDF 的视觉定位、罕见统计设计或任意 JSON Schema；这些限制应在具体任务 uncertainty 中说明。
