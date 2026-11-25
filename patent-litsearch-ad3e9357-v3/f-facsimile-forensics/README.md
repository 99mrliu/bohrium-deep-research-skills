# uspto-facsimile-forensics-lab

源文档取证与版面锚定技能：清点专利输入材料（SHA-256 清单）、从 USPTO 传真版 PDF
提取逐页文本层（poppler 优先、纯标准库回退）、把每项书目事实锚定到
文件＋页＋行/字节区间＋逐字引文、声明并保留 OCR 合并边界、生成传真件与数据库式
记录的差异台账。未声明的模糊匹配一律拒绝；绝不猜测内容。

本技能**不做**：号码归一化/同族合并、检索式设计、法律状态判断、交付契约校验
（均属其他 bundle）。

## Quickstart

```bash
cd skill/

# 1. 自查（全合成夹具，约数秒）
python3 scripts/selfcheck.py

# 2. 对合成夹具跑一遍流水线（产物写入 examples/output/，可随时删除）
python3 scripts/facsimile_register.py --input-dir examples/fixtures --out-dir examples/output/register
PAGES=$(python3 -c "import json;inv=json.load(open('examples/output/register/facsimile_inventory.json'));print('examples/output/register/'+[e['extraction']['pages_file'] for e in inv['files'] if e['kind']=='pdf'][0])")
python3 scripts/page_anchor.py locate --pages "$PAGES" --field publication_number \
  --value "US 2099/0123456 A1" --policy examples/fixtures/anchor_policy.json
```

详见 `examples/example_walkthrough.md`（合成示例）与 `SKILL.md`（完整契约）。

## 布局

- `SKILL.md` — 技能定义与运行时契约
- `scripts/` — 纯标准库 python3 脚本（退出码：0 正常 / 1 检查违例 / 2 用法错误）
- `references/` — PDF 文本层、OCR 边界策略、锚点模式说明
- `examples/` — 合成示例与夹具（全部为虚构内容）
