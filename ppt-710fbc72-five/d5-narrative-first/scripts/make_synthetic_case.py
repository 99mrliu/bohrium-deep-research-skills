#!/usr/bin/env python3
"""make_synthetic_case.py — 生成**合成示例**案例（非正式测试案例，仅供流程演示）。

产物（写入 --outdir，通常是 mktemp 目录）:
  template.pptx   python-pptx 默认模板（真实母版/版式/占位符）
  paper.pdf       matplotlib PdfPages：4 个文本页（含逐字数字）+ 2 个图页（Figure 1/2）
  case.json       {"case_id": "synthetic-demo-05", "output_contract": {...}}
  task.md         明确写明 audience: 研究生组会; duration: 8 minutes; slides: 6-8
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

CASE_ID = "synthetic-demo-05"

P1 = ("LeafNet-S：面向田间部署的轻量级番茄病害识别网络\n"
      "（合成示例论文，仅用于流程演示，无真实科研结论）\n\n"
      "摘要：田间番茄病害识别需要在资源受限设备上兼顾准确率与速度。"
      "本文提出 LeafNet-S，在 12000 张田间图像数据集上达到 87.3% 准确率，"
      "模型体积仅 2.1 MB，单张推理延迟 42 ms。")

P2 = ("1 引言与问题\n\n"
      "番茄病害识别目前依赖人工巡田，成本高且反馈滞后。"
      "已有轻量基线模型 MobileBase-T 在同一田间数据集上仅取得 78.9% 准确率，"
      "难以满足实时部署需求。\n"
      "本文使用的数据集包含 12000 张标注图像，覆盖 5 类常见病害，"
      "其中训练集占 80%，测试集占 20%。")

P3 = ("2 方法\n\n"
      "LeafNet-S 采用深度可分离卷积压缩计算量，"
      "并通过知识蒸馏从准确率 94.1% 的教师模型迁移判别能力。\n"
      "模型在训练集上训练 200 轮，批大小 64，初始学习率 0.001，"
      "采用余弦退火调度。全部实验在单张边缘计算卡上完成。")

P4 = ("3 结果与限制\n\n"
      "LeafNet-S 达到 87.3% 准确率，较基线 78.9% 提升 8.4 个百分点（Figure 1）。\n"
      "单张推理延迟 42 ms，满足田间实时采集需求（Figure 2）。\n"
      "限制：当前模型仅覆盖番茄作物；在强光照变化场景下准确率下降到 81.2%，"
      "跨作物泛化留作后续工作。")

TASK_MD = """# 合成示例任务（synthetic-demo-05，非正式测试案例）

请将本目录中的论文 paper.pdf 组织为一份学术汇报 PPT，使用 template.pptx 作为模板。

audience: 研究生组会
duration: 8 minutes
slides: 6-8

要求：
1. 提取研究问题、方法、结果和限制形成主线。
2. 每页一个主张，保留论文页码/图号证据定位。
3. 按模板生成可编辑 pptx，并导出 PDF/PNG 预览。
"""


def make_template(path: Path) -> None:
    from pptx import Presentation
    prs = Presentation()  # python-pptx 默认模板：真实母版 + 9 个版式 + 占位符
    prs.save(str(path))


_ASCII_TOK = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.%")


def _wrap_cjk(text: str, width: int = 34) -> str:
    """手工换行：优先在标点/空格后断行；绝不把数字/英文 token 从中间劈开（逐字校验需要）。"""
    out_lines = []
    for para in text.split("\n"):
        line = para
        while len(line) > width:
            cut = -1
            for p in "，。；、：） ":
                cut = max(cut, line.rfind(p, 0, width + 1))
            cut = cut + 1 if cut >= 0 else width
            while 0 < cut < len(line) and line[cut - 1] in _ASCII_TOK and line[cut] in _ASCII_TOK:
                cut -= 1
            if cut <= 0:
                cut = width
            out_lines.append(line[:cut])
            line = line[cut:]
        out_lines.append(line)
    return "\n".join(out_lines)


def make_paper(path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib import rcParams
    # 尽量找能显示中文的字体；找不到也能跑（合成示例不依赖中文字形）
    for f in ("PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "SimHei", "DejaVu Sans"):
        try:
            from matplotlib.font_manager import findfont, FontProperties
            if "DejaVu" not in findfont(FontProperties(family=f), fallback_to_default=False):
                rcParams["font.family"] = f
                break
        except Exception:  # noqa: BLE001
            continue
    rcParams["axes.unicode_minus"] = False

    with PdfPages(str(path)) as pdf:
        for text in (P1, P2, P3, P4):
            fig = plt.figure(figsize=(8.27, 11.69))  # A4
            fig.text(0.08, 0.95, _wrap_cjk(text), va="top", ha="left", fontsize=11)
            pdf.savefig(fig)
            plt.close(fig)

        # Figure 1 页：准确率对比柱状图
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        models = ["MobileBase-T\n(baseline)", "LeafNet-S\n(ours)", "Teacher"]
        accs = [78.9, 87.3, 94.1]
        bars = ax.bar(models, accs, color=["#999999", "#2b7bbb", "#d9a441"])
        ax.set_ylabel("Accuracy (%)")
        ax.set_ylim(0, 100)
        for b, a in zip(bars, accs):
            ax.text(b.get_x() + b.get_width() / 2, a + 1, f"{a}%", ha="center", fontsize=12)
        ax.set_title("Test-set accuracy comparison")
        fig.text(0.08, 0.045,
                 "Figure 1: 三种模型在测试集上的准确率对比"
                 "（MobileBase-T 78.9%，LeafNet-S 87.3%，教师模型 94.1%）",
                 fontsize=10)
        pdf.savefig(fig)
        plt.close(fig)

        # Figure 2 页：延迟随批大小变化
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        bs = [1, 2, 4, 8, 16]
        lat = [42, 58, 91, 165, 310]
        ax.plot(bs, lat, marker="o", color="#2b7bbb")
        ax.set_xlabel("Batch size")
        ax.set_ylabel("Latency (ms)")
        ax.axhline(42, ls="--", color="#999999", lw=1)
        ax.annotate("42 ms @ batch=1", xy=(1, 42), xytext=(3, 80),
                    arrowprops=dict(arrowstyle="->", color="#555555"))
        ax.set_title("LeafNet-S inference latency")
        fig.text(0.08, 0.045,
                 "Figure 2: LeafNet-S 单张推理延迟随批大小变化（批大小 1 时延迟 42 ms）",
                 fontsize=10)
        pdf.savefig(fig)
        plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成合成示例案例")
    ap.add_argument("--outdir", required=True, help="输出目录（作为 /input 使用）")
    args = ap.parse_args(argv)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    make_template(out / "template.pptx")
    make_paper(out / "paper.pdf")
    common.write_json(out / "case.json", {
        "case_id": CASE_ID,
        "synthetic": True,
        "note": "合成示例：非正式测试案例，仅供演示流程",
        "materials": ["paper.pdf", "template.pptx"],
        "output_contract": {"fields": ["case_id", "status", "summary", "artifacts",
                                       "evidence_map", "sources", "uncertainty",
                                       "change_log"]},
    })
    (out / "task.md").write_text(TASK_MD, encoding="utf-8")
    print(f"[make_synthetic_case] 合成案例已写入 {out}（case_id={CASE_ID}）")
    print("  template.pptx / paper.pdf(6页, Figure 1-2) / case.json / task.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
