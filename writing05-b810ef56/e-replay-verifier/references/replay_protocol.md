# 可复核性协议（Replay Protocol）

## 1. 角色与信任模型

- **交付方**（加载本 Skill 的 Agent）：产出 /app/output，并用
  pack_manifest.py 把全部可核验承诺固化为
  verification_manifest.json；
- **复核方**（评审、合作者、另一个 Agent）：只信任三样东西——
  原始材料、manifest、verify_pack.py 的输出。复核方**自行**从原始
  材料提取来源文本，不使用交付方提供的提取文本，避免交付方在
  文本层做手脚。

## 2. manifest 承诺项

| 类别 | 承诺 | 复核动作 |
|---|---|---|
| HASH | 产物文件字节级未变 | 重算 SHA-256 比对 |
| QUOTE | 摘录是来源原文的连续子串 | 规范化（NFKC+空白折叠）后逐字重查 |
| NUMBER | 关键数字在来源中逐字出现 | 重新命中检查 |
| REF | 文献条目著录字段完整 | title + authors/year 完整性 |
| CONTRACT | result.json 合法、case_id 一致、契约键齐全 | 重新解析逐项核对 |

## 3. 交付方操作规程

1. 写作完成后，先把证据承诺整理成 evidence JSON（quotes/numbers/
   refs，source 用来源文件名主体）；
2. 运行 pack_manifest.py 生成 manifest 到 /app/output；
3. 运行 verify_pack.py 自检（sources 指向自己提取的文本目录）；
4. 有 FAIL 必须修复后重跑，全 PASS 才算交付完成；
5. result.json 的 change_log 记录自检通过时间，limits 说明
   manifest 未覆盖的部分（见第 5 节）。

## 4. 复核方操作规程

```bash
python3 verify_pack.py --output-dir /app/output \
    --sources <复核方自提取的文本目录> \
    --manifest /app/output/verification_manifest.json \
    --report verify_report.md
```
退出码 0 = 全部承诺通过；1 = 存在未通过项（报告逐项列出）。

## 5. 覆盖范围与诚实声明

manifest 只覆盖**登记过的**承诺。复核能证明"登记的摘录/数字/
文献是真的"，不能证明"没有遗漏重要证据"或"语义支持关系正确"——
前者靠论断清单的完整性自查，后者仍是模型与人工的判断责任。
交付方应在 limits 中写明：哪些内容进入了 manifest（可机器复核），
哪些没有（只能人工复核）。打包后再改动 /app/output 的任何文件
都会使 HASH 检查失败——这是特性：改动后必须重新生成 manifest。
