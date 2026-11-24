# 最小调用示例

> **合成示例，非平台案例结果。** 以下输入由 `make_synthetic_case.py` 现场生成，
> 全部文字为虚构（"Synth et al."/"fictional"/"synthetic"），仅用于演示调用方式。

```bash
BUNDLE=/path/to/c-native-edit-proofer/skill
RUN=/path/to/c-native-edit-proofer/runs/c

# 1. 生成合成输入与 deck.json 内容源（含真表格数据、fig1.png + sidecar）
python3 $BUNDLE/examples/make_synthetic_case.py --out-dir $RUN/input
python3 $BUNDLE/examples/make_deck_json.py --paper $RUN/input/paper.pdf \
    --data $RUN/input/data.csv --fig-dir $RUN/work/figs --out $RUN/work/deck.json

# 2. 字体探测 → 证据逐字扫描
python3 $BUNDLE/scripts/font_probe.py --report $RUN/work/font_report.json
python3 $BUNDLE/scripts/evidence_scan.py --paper $RUN/input/paper.pdf \
    --deck $RUN/work/deck.json --report $RUN/work/evidence_scan.json

# 3. 原生构建（真 table shape、图片+sidecar、备注、证据页脚）
python3 $BUNDLE/scripts/build_native.py $RUN/work/deck.json \
    --template $RUN/input/target-template.pptx --fig-dir $RUN/work/figs \
    --fonts $RUN/work/font_report.json \
    --out $RUN/output/presentation.pptx --report $RUN/work/build_report.json

# 4. 三道验证门禁
python3 $BUNDLE/scripts/edit_lint.py $RUN/output/presentation.pptx \
    --report $RUN/work/editability_report.json        # 有 error 退出 1
python3 $BUNDLE/scripts/roundtrip_check.py $RUN/output/presentation.pptx \
    --report $RUN/work/roundtrip_report.json --expect $RUN/work/build_report.json
python3 $BUNDLE/scripts/render_diff.py $RUN/output/presentation.pptx \
    --out-dir $RUN/output/render --report $RUN/work/render_report.json \
    --profile /tmp/lo-c                                # 无 soffice → tool_missing

# 5. 汇总 result.json（字段名读自 case.json output_contract）
python3 $BUNDLE/scripts/make_result.py --case $RUN/input/case.json \
    --deck $RUN/work/deck.json --work-dir $RUN/work \
    --output-dir $RUN/output --out $RUN/output/result.json
```

预期：edit_lint / roundtrip_check / render_diff 退出 0，result.json `status`
为 `success`，8 项 compliance_checks 全 pass，`content_map` 每条 quote 都被
evidence_scan 逐字命中。
