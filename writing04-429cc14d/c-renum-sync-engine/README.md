# renum-sync-engine

确定性参考文献编号更新与交叉引用同步引擎（Skill 竞赛 bundle，方向 C：
编号更新与交叉引用结构工程）。

**核心立场**：编号一致性不靠人眼核对。稿件+文献表建成稳定 ID 的引用图，
所有修改是事务性编辑操作，编号永远由「全局首现顺序」重算，正文标记、文末
列表、图表注、脚注、附录一次同步。`original-label → stable-id → new-label`
三层映射全程留痕，旧编号绝不按位置猜。

## 组成

| 路径 | 作用 |
| --- | --- |
| `SKILL.md` | 技能说明：运行时契约、五阶段流程、V1–V8、异常处理表 |
| `scripts/cite_scan.py` | 扫描建图：occurrences.jsonl + labels.json（含悬空/未引用清单） |
| `scripts/renumber.py` | `plan` 按 ops.json 重算映射；`apply` 复算校验后原子落盘 |
| `scripts/sync_verify.py` | V1–V8 双向一致性核验，违规则退出码 1 |
| `references/renumber_model.md` | 引用图模型与规则细则 |
| `references/file_formats.md` | 各 JSON/JSONL 字段级格式与退出码 |
| `examples/` | 全虚构合成示例 + 真实运行产物（含 booby-trap 捕获证据） |

## 30 秒跑通（本地相对路径；评测环境用 /skills/weekly-skill/scripts/…）

```bash
python3 scripts/cite_scan.py --manuscript examples/input/manuscript.txt \
  --references examples/input/references.txt --out /tmp/work
python3 scripts/renumber.py plan --manuscript examples/input/manuscript.txt \
  --references examples/input/references.txt --ops examples/input/ops.json \
  --style numeric-bracket --out /tmp/work
python3 scripts/renumber.py apply --manuscript examples/input/manuscript.txt \
  --references examples/input/references.txt --label_map /tmp/work/label_map.json \
  --style numeric-bracket --out /tmp/out
python3 scripts/sync_verify.py --manuscript /tmp/out/edited_manuscript.txt \
  --references /tmp/out/edited_references.txt --label_map /tmp/out/label_map.json \
  --out /tmp/out   # 全过则退出码 0
```

特性：仅标准库、无网络、确定性（同输入同输出）、apply 原子（校验不过不写文件）、
V8 幂等自证（空 ops 重跑零变化）。支持顺序编码制（[n] / ^[n]^ 上标约定）与
著者-出版年制（列表字母序重排 + 同年 a/b 后缀回改）。
