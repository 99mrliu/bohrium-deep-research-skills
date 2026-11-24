# output_contract → result.json 填充规则与诚实 partial 语义

本文件是 `scripts/assemble_result.py` 与 `scripts/verify_delivery.py` 的语义依据。
所有字段**运行时从 case.json 的 `output_contract.fields` 读取**，禁止硬编码字段名。

## 1. result.json 顶层结构

| 键 | 来源 | 规则 |
|-|-|-|
| `case_id` | case.json | 必须逐字相等（门 G2 / 检 C2） |
| `task` | case.json | 原样拷贝 |
| `status` | 计算 | `complete` / `partial` / `failed`，见 §3 |
| `<field>` × N | result_parts | 每个契约字段一个键，见 §2 |
| `artifacts` | `artifacts.json` | 交付文件相对路径列表（相对输出目录），每个文件必须真实存在（门 G4） |
| `sources` | `sources.json` | 实际使用过的输入材料清单；没有则为 `[]` |
| `problems` | 装配过程 | 门故障记录，见 §3；无问题为 `[]` |
| `limits` | 装配/渲染过程 | 诚实限制（降级、渲染器不可用、跳过渲染等） |
| `note` | `--note` 参数 | 可选；合成示例必带标记 |

## 2. result_parts 约定（模型唯一需要遵守的写盘格式）

对工作目录下 `result_parts/`，每个契约字段写**恰好一个**零件文件：

- `<field>.json`：结构化值（对象/列表/字符串均可），必须可解析（门 G6）。
- `<field>.md`：纯文本/markdown，整文件内容作为该字段的字符串值。

保留文件名（不得用作契约字段名）：

- `_meta.json`：`{"case_id": "...", "status": "complete|partial|failed"}`。
  `case_id` 若写，必须与 case.json 一致（门 G2）。
- `artifacts.json`：JSON 字符串列表，相对输出目录的路径，如
  `["chapters/ch01.md", "preview/edited_chapters.pdf"]`。**只列真实存在的文件**。
- `sources.json`：JSON 字符串列表。

### 常见字段的语义映射（字段名 → 零件内容）

| 字段名 | 推荐零件 | 内容形态 |
|-|-|-|
| `edited_chapters` | `.json` | 对象：`{"ch01.md": "chapters/ch01.md", ...}`，值为输出目录内相对路径；指向的文件必须存在且与 `/app/work/chapters/` 最新副本逐字节一致（检 C5） |
| `change_record` | `.md` | 每条编辑：改了什么、在哪、依据工单哪条、验收判据 |
| `consistency_report` | `.md` | 术语/引用/编号/单位的跨章一致性结论；无发现也要写"未发现不一致" |
| `uncertainty` | `.md` | 低置信项、无法核验的论断、待确认问题；没有则写"无" |
| `deliverable` / `evidence` / 其他 | `.md` 或 `.json` | 按字段名语义填充；语义对不上时见 SKILL.md 异常矩阵第 3 条 |

**契约字段与产出物语义不匹配时的映射规则**：字段名要求 X 而实际只产出 Y 时，
宁可填"Y 的如实内容 + problems 说明缺口"，也不得把无关内容改名冒充 X；
完全无法产出时填 `null` + problem（门 G1 自动完成）。

## 3. 诚实 partial 语义

- `problems` 非空 ⇒ `status` 至多为 `partial`；`_meta.json` 声明 `complete`
  会被强制降级为 `partial` 并记入 `limits`（门 G5）。
- 字段值为 `null` 必须在 `problems` 中有对应 `field` 的记录，否则终检 C3 失败
  ——"静默 null" 等同于隐瞒。
- **先存 partial 再改进**：任何时候运行 `assemble_result.py` 都会落盘一个可解析的
  result.json（哪怕全字段 null）。时间不足时应立即装配当前状态，再增量补零件重跑。
- `status=failed` 仅用于 case.json 不可读等无法开工的情形。

## 4. 提到的路径必须真实（门 G3）

任何零件文本中出现的 `/app/output/...` 字面值都会被提取并核验真实存在。
因此：写到 change_record 等文本里的交付路径，必须先落盘再提及；
不要写"将交付""见附录 X"之类指向不存在文件的句子。
