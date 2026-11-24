# examples/minimal — 合成示例 / SYNTHETIC example

**Both source texts are fabricated** to implant known register violations.
They are not real manuscripts. All outputs in `out/` are produced by actually
running `sh run.sh` (deterministic: re-running yields byte-identical files).

Implanted violations:

- `source-zh-grant.txt` (基金申请书): 口语化“搞/挺/特别”，宣传化“国际领先/
  填补空白”（基金中记 warning），绝对化“彻底解决/绝对不会”。
- `source-en-abstract.txt` (英文摘要): contractions (`doesn't`, `it's`),
  `get improved`, `a lot of`, `really`, 人称误用 `I`, 宣传化 `cutting-edge`,
  绝对化 `never`。

Run:

```sh
cd examples/minimal && sh run.sh    # expected exit code 0
```

What to inspect:

- `out/result.json` → `register_report.*.before.violations` hits every
  implanted violation; `after.total_violations` is 0 for both texts.
- `out/register-scorecard.md` → before/after tables, both gates `PASS`.
- `out/changes.json` → 5 applied edits plus 2 **deliberate reverts** proving
  the gates: an unreviewed edit (`reverted-unreviewed`, zh s0001) and an edit
  dropping protected tokens `3` / `12.5%` (`reverted-protected-token`,
  en s0004).
- `out/polished.md` → full polished texts; `Figure 2 [7]`, `3`, `12.5%`
  untouched.

`edits.json` stands in for agent decisions (type + reason + review record);
in a real run the agent writes these batches itself.
