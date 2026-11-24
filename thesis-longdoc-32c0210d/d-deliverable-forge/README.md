# deliverable-forge

玻尔 Playground 竞赛题 challenge-32c0210d（学位论文与长文档写作）五方向 Skill 束之
**下游交付与渲染工程** bundle。

把"交付"本身工程化，杜绝两类经典翻车：**声称交付了但路径不存在**、**预览是伪造的**。

## 四个脚本（python3 标准库，路径全参数化）

| 脚本 | 干什么 | 替模型省了什么 |
|-|-|-|
| `scripts/contract_checklist.py` | case.json → checklist.json，运行时读取 `output_contract.fields` | 不用手抄契约字段，不漏键 |
| `scripts/assemble_result.py` | result_parts/ → result.json，六道硬门（契约键/case_id/幽灵路径/artifact 存在性/状态一致性/JSON 可解析），原子写 | 诚实 partial 自动落盘，exit≠0 时问题已显式记录 |
| `scripts/render_preview.py` | 改后章节 → 真实 PDF + 首页 PNG；pandoc→xelatex→soffice 降级链，各带 timeout；全灭则 limits 记 `renderer_unavailable`，绝不伪造；`FORGE_NO_RENDER=1` 确定性跳过 | 不用手装排版工具链，渲染失败不阻塞交付 |
| `scripts/verify_delivery.py` | 交付终检 + sha256 manifest：契约键齐全（null 须有 problem 记录）、preview 文件必须非空、交付章节与工作副本逐字节一致 | 一键回答"这次交付到底能不能交" |

## 快速验证

```bash
cd examples/synthetic
./run_example.sh          # 端到端：checklist→模拟编辑→assemble→渲染(确定性跳过)→终检→故障注入
```

`examples/synthetic/` 为**合成示例**（自造三章短文，与任何真实论文无关），
`expected/` 由真实运行固化，所有示例产物带 `SYNTHETIC EXAMPLE` 标注。
真实渲染分支用法见 `references/renderers.md`。

## 文档

- `SKILL.md` — 可直接照做的命令序列（输入契约/工作流/输出契约/异常矩阵/边界）
- `references/output_contract.md` — result.json 逐字段填充规则与诚实 partial 语义
- `references/renderers.md` — 渲染器探测顺序、失败降级、预览命名约定
