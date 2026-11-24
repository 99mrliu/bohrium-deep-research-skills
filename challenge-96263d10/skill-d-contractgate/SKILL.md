---
name: contract-gate-run-discipline
description: 学术格式与模板适配——契约门禁运行纪律（过程质量控制）。不发明新的排版技术，而是保证任何模板适配任务在平台契约下可交付、可复核、可中断恢复：probe 第一分钟落 partial result.json 骨架（case_id+全部 output_contract 字段+输入固证），checkpoint 给每个阶段打卡（产物 sha256+运行日志），seal 独立八项裁决（契约字段非空、status 与证据一致、产物哈希匹配、来源与改动可回溯）不过不交付，900 秒预算阶梯任何时刻中断都有诚实 partial。纯 Python 3 标准库。适合作为模板适配、格式转换、学术写作交付类任务的运行骨架。
---

# 契约门禁运行纪律（contract-gate：不过门，不交付）

版本 1.0。重心：**过程质量**。低分运行的共同死因不是不会排版，而是
result.json 契约字段缺失、status 虚报、产物哈希对不上、中断后什么都没有。
本 Skill 把契约合规做成三道机器工序。契约要点与预算阶梯见
`references/run-contract.md`。

以下 `$SK` 指本 SKILL.md 所在目录（平台安装为 `/skills/weekly-skill`，先 `ls /skills/` 确认）。

## 运行契约（平台约定，本 Skill 强制执行）

- 输入 `/input/case.json` + `/input/task.md` + 材料；工作区 `/app/work`；交付 `/app/output`。
- result.json：`case_id` + `output_contract` **全部字段** + status/sources/changes/
  uncertainties/limits/artifacts；partial 必须指明局限；三种失败（材料缺失/
  无法判断/运行失败）分别说明。
- 可编辑产物附真实渲染 PDF/PNG；渲染不可用写 limits，不伪造。
- 预算 64 请求 / 900 秒：按 T0–T5 阶梯执行（见 references），随时可中断。

## 三道工序

### 第 0 分钟：probe（骨架先行）
```bash
python3 $SK/scripts/probe.py --input /input --work /app/work --output /app/output
```
盘点输入（sha256 + magic 嗅探）→ 宽容解析 case.json → **立即写 partial
result.json 骨架**（契约字段空值占位、status=partial、limits=["run started"]）。
case.json 损坏时骨架照落、status=failed、退出码 2——failed 也是诚实交付。
随后读 task.md 与材料实际内容，再决定适配技术路线（本 Skill 不规定）。

### 每阶段结束：checkpoint（打卡固证）
```bash
python3 $SK/scripts/checkpoint.py --work /app/work --output /app/output \
    --stage adapt --note "样式重绑完成" --artifact /app/output/交付件.docx
```
产物哈希进 result.json.artifacts，事件进 journal.jsonl，阶段进 run_state.json。
**拒绝登记不存在的产物**（退出码 2）——幽灵产物在第一现场被拦。

### 交付前：seal（独立封印）
```bash
python3 $SK/scripts/seal.py --case /input/case.json --output /app/output --work /app/work
```
八项独立裁决（S1 可解析 / S2 case_id / S3 契约字段非空 / S4 status 与证据一致 /
S5 产物哈希 / S6 来源非空 / S7 改动记录 / S8 有真实交付物）。
**SEAL REFUSED 就按清单修交付物，直到 SEALED；不许改 seal 迁就交付物。**

## 异常处理

| 情况 | 处置 |
|---|---|
| case.json 损坏 | probe 骨架已落（status=failed），limits 记录错误，照实结束 |
| output_contract 形态异常（字符串/嵌套） | probe/seal 三种形态都认；认不出的字段名进 manual_confirm |
| 适配中途时间耗尽 | 最后完成的 checkpoint 即为交付状态；limits 写清未到梯级 |
| 产物在 seal 前被手工改过 | S5 哈希不匹配 → REFUSED；重跑 checkpoint 重新固证 |
| 想交 complete 但还有未确认项 | S4 拦截：先落实未确认项，或诚实交 partial |
| 渲染不可用 | limits 声明后 S8 认可；但 limits 里有声明时 status 只能是 partial |

## 资源清单（均在 `$SK/` 下）

| 路径 | 作用 |
|---|---|
| `scripts/probe.py` | 输入固证 + 契约抽取 + partial 骨架（第 0 分钟） |
| `scripts/checkpoint.py` | 阶段打卡 + 产物哈希登记 + 运行日志 |
| `scripts/seal.py` | 交付八项独立裁决（SEALED / SEAL REFUSED） |
| `references/run-contract.md` | 平台契约要点、T0–T5 预算阶梯、status 语义 |
| `examples/run_demo.sh` | 合成示例一键演示（正路 SEALED + 反路 REFUSED 实录） |

## 自查清单（交付前）

1. journal.jsonl 连续记录 probe→…→seal，无缺段。
2. seal_report.json 八项全 PASS。
3. result.json 每个 artifacts 条目哈希与盘上文件一致（S5 已过）。
4. status 诚实：有未了事项就是 partial。
