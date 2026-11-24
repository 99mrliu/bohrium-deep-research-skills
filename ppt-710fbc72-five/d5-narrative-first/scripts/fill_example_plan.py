#!/usr/bin/env python3
"""fill_example_plan.py — 为**合成示例**案例自动填写 storyline.json + slide_plan.json。

仅用于 examples/run_example.sh 的非交互演示：读取 work/paper/source_index.json 拿到
Figure 1/2 的真实抽取路径，并按源文本逐字数字写 bullets；notes 长度刻意不一，
使 plan_lint 的计时预算（8min±15%）可被真实地计算出来。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

STORYLINE = {
    "_synthetic": True,
    "mainline": {
        "problem": "田间番茄病害识别依赖人工巡田，成本高且滞后；轻量基线仅 78.9% 准确率，无法满足实时部署。",
        "method": "LeafNet-S 用深度可分离卷积压缩计算量，并从 94.1% 准确率的教师模型做知识蒸馏。",
        "results": "在 12000 张图像上达 87.3% 准确率（+8.4 个百分点）、体积 2.1 MB、单张延迟 42 ms。",
        "limitations": "仅覆盖番茄作物；强光照变化下准确率下降到 81.2%，跨作物泛化留作后续工作。",
    },
    "audience": "研究生组会",
    "duration_min": 8,
    "claims": [
        {"id": "c1", "text": "LeafNet-S 面向田间部署，在 12000 张图像上达 87.3% 准确率且体积仅 2.1 MB",
         "evidence_refs": [{"type": "page", "ref": "p.1",
                            "quote": "87.3% 准确率"}],
         "depends_on": []},
        {"id": "c2", "text": "人工巡田滞后且基线 MobileBase-T 仅 78.9%，田间实时识别仍是未解问题",
         "evidence_refs": [{"type": "page", "ref": "p.2",
                            "quote": "78.9% 准确率"}],
         "depends_on": []},
        {"id": "c3", "text": "深度可分离卷积加知识蒸馏（教师 94.1%）在压缩计算量的同时迁移判别能力",
         "evidence_refs": [{"type": "page", "ref": "p.3",
                            "quote": "94.1% 的教师模型"}],
         "depends_on": ["c2"]},
        {"id": "c4", "text": "LeafNet-S 准确率 87.3%，较基线 78.9% 提升 8.4 个百分点",
         "evidence_refs": [{"type": "page", "ref": "p.4", "quote": "提升 8.4 个百分点"},
                           {"type": "figure", "ref": "Figure 1",
                            "quote": "LeafNet-S 87.3%"}],
         "depends_on": ["c3"]},
        {"id": "c5", "text": "单张推理延迟 42 ms，满足田间实时采集需求",
         "evidence_refs": [{"type": "page", "ref": "p.4", "quote": "推理延迟 42 ms"},
                           {"type": "figure", "ref": "Figure 2", "quote": "延迟 42 ms"}],
         "depends_on": ["c3"]},
        {"id": "c6", "text": "模型仅覆盖番茄，强光照变化下准确率下降到 81.2%",
         "evidence_refs": [{"type": "page", "ref": "p.4",
                            "quote": "下降到 81.2%"}],
         "depends_on": ["c4", "c5"]},
        {"id": "c7", "text": "边缘设备上准确率与延迟可兼顾，跨作物泛化是下一步",
         "evidence_refs": [{"type": "page", "ref": "p.4",
                            "quote": "跨作物泛化留作后续工作"}],
         "depends_on": ["c4", "c5", "c6"]},
    ],
}

# notes 长短刻意不一（约 55/85/100/75/60/70/50 秒量级），用于演示计时预算的真实计算
NOTES = {
    1: "各位同学好，今天组会我汇报一篇田间番茄病害识别的工作，LeafNet-S。"
       "先看它的定位：这是一篇典型的边缘部署导向的论文，评价标准不是单一准确率，"
       "而是准确率、模型体积、推理速度三者的权衡。摘要里三个数字先记住："
       "一万两千张图像的数据集、百分之八十七点三的准确率、二点一兆的模型体积。"
       "我的汇报按问题、方法、结果、限制四部分展开，总共大约八分钟，"
       "中间随时可以打断提问。这篇工作和我们组在做的田间病害项目关联很直接，"
       "所以今天除了把方法和数字讲清楚，我还会把作者自己写明的两条限制单独拿出来讨论，"
       "看看哪些坑是我们在自己的项目里可以提前避开的。",
    2: "先看问题本身。番茄种植里病害识别长期靠人工巡田：人走进大棚逐株检查，"
       "成本高、覆盖低，而且反馈滞后，发现病斑时往往已经错过最佳防治窗口。"
       "这篇论文把问题形式化为五类常见病害的图像分类任务，数据集是一万两千张田间标注图像，"
       "八成做训练、两成做测试，采集自真实大棚而非摆拍。那现有方案差在哪？"
       "作者复现的轻量基线 MobileBase-T 在这份数据上只有百分之七十八点九的准确率，"
       "离田间可用的门槛差距明显；更要命的是延迟，稍大一点的模型在边缘卡上根本跑不动实时。"
       "所以这篇工作的目标函数很清楚：在资源受限设备上，把准确率提上去，同时把延迟压下来。"
       "这个目标直接决定了后面方法部分的每一个设计选择。"
       "这里我想多强调一句数据集：一万两千张图全部来自真实大棚的巡检拍摄，"
       "光照、角度、遮挡都和田间实际情况一致，这比摆拍数据集难得多，"
       "也是基线只有七成多准确率的原因之一——问题本身并不简单。",
    3: "方法部分有两个关键选择，我先讲结构再讲训练。第一，主干网络全部换成深度可分离卷积："
       "把标准卷积拆成逐通道卷积加点卷积两步，计算量和参数量成倍下降，"
       "这是模型能压到二点一兆的主要手段。但结构压缩必然损失精度，所以第二个选择是知识蒸馏："
       "用一个准确率百分之九十四点一的大教师模型，让学生在拟合真实标签的同时对齐教师的软标签分布，"
       "把压缩丢掉的判别能力买回来。训练细节上，模型在训练集上跑两百轮，批大小六十四，"
       "初始学习率零点零零一，配合余弦退火调度，全部实验在单张边缘计算卡上完成，"
       "这也说明方法本身对算力要求不高，实验室可以复现。"
       "可能有同学会问为什么不直接上量化或者剪枝：作者的思路是先换更省的结构，"
       "蒸馏负责兜住精度，量化和剪枝在这个框架里是可以继续叠加的，并不冲突。"
       "一句话总结方法：先用结构把成本压到底，再用蒸馏把精度买回来。",
    4: "结果先看准确率这一维。请大家看图一的柱状对比：基线 MobileBase-T 百分之七十八点九，"
       "教师模型百分之九十四点一，LeafNet-S 落在百分之八十七点三，"
       "比基线整整高八点四个百分点。这个提升的含金量在于前提——模型体积只有二点一兆，"
       "也就是用教师模型零头的体积，换回了教师百分之九十以上的精度水平。"
       "从蒸馏的角度看，学生到教师之间还有约七个百分点差距，"
       "说明继续压榨蒸馏策略仍有空间。要提醒大家的是，论文只报了整体准确率，"
       "没有给五个病害类别的逐类指标，读这篇工作时这一点要留意，"
       "某些少数类的表现可能被平均数掩盖。"
       "另外补充一点：这八点四个百分点的提升是在同一份训练集、同一份测试集、"
       "同样的训练预算下拿到的对比，实验设置是公平的，数字是可信的。",
    5: "再看速度这一维。图二是推理延迟随批大小变化的曲线：批大小为一时单张延迟四十二毫秒，"
       "批越大延迟越高，十六张时已经到三百多毫秒。为什么关键看批大小一？"
       "因为田间采集基本是摄像头触发一张处理一张，实时性由单张延迟决定，"
       "四十二毫秒意味着每秒可以处理二十张以上，完全跟得上巡航拍摄的节奏。"
       "把图一和图二放在一起看，这篇工作的闭环才算完整："
       "准确率提了八点四个百分点，延迟还压在实时线以内。"
       "再补一个部署视角的观察：四十二毫秒意味着一块边缘卡可以同时服务多路摄像头轮询，"
       "对一个标准大棚的巡检节奏来说，算力是绰绰有余的，"
       "这也让后面讨论落地成本时有了一个比较扎实的底数。",
    6: "限制部分作者写得比较诚实，也是我们最该带走的信息。第一，模型目前只覆盖番茄一种作物，"
       "跨作物泛化完全没有验证，直接搬到黄瓜、辣椒上效果未知；"
       "第二，在强光照变化的场景下准确率掉到百分之八十一点二，"
       "比标准条件低了六个百分点多，说明模型对采集条件敏感，"
       "数据增强策略或者采集协议都还有改进空间。"
       "这两个限制恰好是我们组病害项目可以直接借鉴的教训："
       "采集协议要先固定，跨作物要单独建评测。"
       "我个人的判断是，第一个限制是工程问题，堆数据就能缓解；"
       "第二个限制更接近模型鲁棒性的本质，可能要在增强策略之外引入域适应的方法，"
       "这也可能是我们后续和作者方向合作的一个切入点。",
    7: "最后总结。这篇工作证明了一件事：在边缘设备上，准确率和延迟是可以兼顾的，"
       "关键数字是两个——准确率提升八点四个百分点，单张延迟四十二毫秒；"
       "方法的启示是结构压缩加知识蒸馏这条组合拳；"
       "限制在跨作物泛化和光照鲁棒性，留给了后续工作也留给了我们。"
       "如果把这篇工作映射到我们自己的项目上，我建议下一步先做两件事："
       "一是按它的采集协议补齐我们的田间数据，二是把深度可分离卷积加蒸馏的组合"
       "在我们的作物上做一次小规模验证。"
       "我的汇报到这里，全程大约八分钟，谢谢大家，欢迎提问和讨论。",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="填写合成示例的 storyline + slide_plan")
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    work = Path(args.work)
    src = common.read_json(work / "paper" / "source_index.json", {}) or {}
    figs = {f["label"]: f for f in src.get("figures", [])}
    if "Figure 1" not in figs or "Figure 2" not in figs:
        print("[fill_example_plan] source_index 中缺 Figure 1/2，请先运行 prepare")
        return 1

    def fig(label):
        f = figs[label]
        return {"ref": label, "path": f["path"], "caption": f"{label}: {f['caption']}"}

    slides = [
        {"kind": "title", "title": "LeafNet-S：面向田间部署的轻量级番茄病害识别",
         "claim_id": "c1", "claim": next(c["text"] for c in STORYLINE["claims"] if c["id"] == "c1"),
         "bullets": [], "figures": [],
         "evidence": [{"type": "page", "ref": "p.1", "quote": "2.1 MB"}],
         "notes": NOTES[1], "layout_hint": "Title Slide"},
        {"kind": "background", "title": "背景：田间实时病害识别仍是未解问题",
         "claim_id": "c2", "claim": next(c["text"] for c in STORYLINE["claims"] if c["id"] == "c2"),
         "bullets": ["病害识别依赖人工巡田，成本高、反馈滞后",
                     "基线 MobileBase-T 仅取得 78.9% 准确率",
                     "数据集 12000 张标注图像，覆盖 5 类病害"],
         "figures": [],
         "evidence": [{"type": "page", "ref": "p.2", "quote": "12000 张标注图像"}],
         "notes": NOTES[2], "layout_hint": "Title and Content"},
        {"kind": "method", "title": "方法：结构压缩 + 知识蒸馏",
         "claim_id": "c3", "claim": next(c["text"] for c in STORYLINE["claims"] if c["id"] == "c3"),
         "bullets": ["深度可分离卷积压缩计算量与参数量",
                     "知识蒸馏自准确率 94.1% 的教师模型",
                     "训练 200 轮，批大小 64，初始学习率 0.001"],
         "figures": [],
         "evidence": [{"type": "page", "ref": "p.3", "quote": "批大小 64"}],
         "notes": NOTES[3], "layout_hint": "Title and Content"},
        {"kind": "results", "title": "结果一：准确率提升 8.4 个百分点",
         "claim_id": "c4", "claim": next(c["text"] for c in STORYLINE["claims"] if c["id"] == "c4"),
         "bullets": ["LeafNet-S 达 87.3% 准确率，基线为 78.9%",
                     "模型体积仅 2.1 MB，约为教师的零头"],
         "figures": [fig("Figure 1")],
         "evidence": [{"type": "figure", "ref": "Figure 1", "quote": "LeafNet-S 87.3%"}],
         "notes": NOTES[4], "layout_hint": "Title and Content"},
        {"kind": "results", "title": "结果二：单张推理延迟 42 ms",
         "claim_id": "c5", "claim": next(c["text"] for c in STORYLINE["claims"] if c["id"] == "c5"),
         "bullets": ["单张推理延迟 42 ms，满足田间实时采集",
                     "延迟随批大小上升，田间场景关键看批大小 1"],
         "figures": [fig("Figure 2")],
         "evidence": [{"type": "figure", "ref": "Figure 2", "quote": "延迟 42 ms"}],
         "notes": NOTES[5], "layout_hint": "Title and Content"},
        {"kind": "discussion", "title": "讨论：两条明确的限制",
         "claim_id": "c6", "claim": next(c["text"] for c in STORYLINE["claims"] if c["id"] == "c6"),
         "bullets": ["仅覆盖番茄作物，跨作物泛化未验证",
                     "强光照变化下准确率下降到 81.2%"],
         "figures": [],
         "evidence": [{"type": "page", "ref": "p.4", "quote": "下降到 81.2%"}],
         "notes": NOTES[6], "layout_hint": "Title and Content"},
        {"kind": "conclusion", "title": "结论：准确率与延迟可以兼顾",
         "claim_id": "c7", "claim": next(c["text"] for c in STORYLINE["claims"] if c["id"] == "c7"),
         "bullets": ["87.3% 准确率与 42 ms 延迟同时达成",
                     "后续：跨作物泛化与光照鲁棒性"],
         "figures": [],
         "evidence": [{"type": "page", "ref": "p.4", "quote": "跨作物泛化留作后续工作"}],
         "notes": NOTES[7], "layout_hint": "Title and Content"},
    ]
    common.write_json(work / "storyline.json", STORYLINE)
    common.write_json(work / "slide_plan.json",
                      {"_synthetic": True, "filled_by": "fill_example_plan.py",
                       "slides": slides})
    print(f"[fill_example_plan] storyline.json（{len(STORYLINE['claims'])} claims）"
          f"与 slide_plan.json（{len(slides)} 页）已写入 {work}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
