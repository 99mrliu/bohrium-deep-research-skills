# SYNTHETIC / 合成示例

This is a wholly synthetic, runnable example—not a scientific claim or a real presentation.

Run from the bundle root with an external writable artifact directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_synthetic.py --output-root /app/work/native-synthetic
```

The runner uses ReportLab only to generate a four-page synthetic paper with Figure 1 and results text. It also generates:

1. a real PPTX template with a modified theme and multiple native layouts;
2. a three-slide starting deck containing keep, edit, and remove candidates;
3. `case.json` and `task.md` requesting adaptation to exactly five slides, seven minutes, and a fixed audience.

It then runs `prepare`, selects exact extracted `quote_id` spans, writes a valid plan, runs `finish`, and asserts:

- editable PPTX plus five real PDF pages and five real PNGs;
- consistent PDF and PNG dimensions and retained expected text;
- slide→layout→master→theme chain membership;
- unchanged theme and slide dimensions;
- byte-identical retained slide XML and relationships;
- semantic output-contract fields;
- rejection of a plan missing one original slide and of layout index `9999`.

The primary deliverables are under `OUTPUT_ROOT/output`; negative-test results are under `OUTPUT_ROOT/negative-output`; `synthetic_test_summary.json` summarizes assertions. The script marks visual review `automated`, not `complete`: an agent must open every page image before making a human/visual completeness claim. No generated binary is stored in this Skill bundle.
