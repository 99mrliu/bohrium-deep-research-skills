#!/usr/bin/env python3
"""render_preview.py — 思维导图确定性预览渲染（matplotlib，可优雅降级）。

用法:
    python3 scripts/render_preview.py --map mindmap.json --outdir OUT

布局算法（确定性，无任何随机性）:
    - 左向右整齐树布局；子节点按 id 字典序排列；
    - 叶节点按深度优先顺序依次分配整数 y 坐标（0, 1, 2, ...）；
    - 内部节点 y = 其全部子节点 y 的算术平均（垂直居中于子树）；
    - x = depth * spacing，spacing 由全局最长标签推导；
    - 父子之间绘制肘形（elbow）连接线；
    - relations 以红色虚线弧线绘制，中点处标注关系类型。

输出:
    mindmap.png          dpi=150 位图预览
    mindmap.pdf          矢量预览
    render_manifest.json 渲染清单（工具版本、字体选择、画布尺寸、状态）

若 matplotlib 不可用：仅写 render_manifest.json（status=skipped_no_matplotlib）
并以退出码 0 结束，不中断整体流程。
"""
import argparse
import json
import os
import platform
import sys

CJK_CANDIDATES = [
    "Noto Sans CJK SC", "Noto Sans CJK JP", "PingFang SC",
    "Hiragino Sans GB", "WenQuanYi Zen Hei", "SimHei",
    "Microsoft YaHei", "Arial Unicode MS",
]
DPI = 150


def load_map(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    nodes = {n["id"]: n for n in data["nodes"]}
    children = {nid: [] for nid in nodes}
    for n in data["nodes"]:
        p = n.get("parent")
        if p is not None:
            children[p].append(n["id"])
    for k in children:
        children[k].sort()
    relations = sorted(
        data.get("relations", []),
        key=lambda r: (r["from"], r["to"], r.get("type", "")),
    )
    return data["root"], nodes, children, relations


def write_manifest(path, **kw):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(kw, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def base_manifest(nodes, relations):
    return {
        "tool_versions": {"python": platform.python_version(),
                          "matplotlib": None},
        "font": {"requested_cjk": CJK_CANDIDATES, "chosen": None,
                 "fallback": True},
        "nodes": len(nodes),
        "relations": len(relations),
        "canvas": {"width_px": None, "height_px": None},
    }


def compute_layout(root, nodes, children):
    """返回 (pos, max_depth, n_leaves)；pos[id] = (x_depth, y)。"""
    pos = {}
    counter = [0]
    max_depth = [0]

    def rec(nid, depth):
        max_depth[0] = max(max_depth[0], depth)
        kids = children.get(nid, [])
        if not kids:
            pos[nid] = (depth, float(counter[0]))
            counter[0] += 1
        else:
            for c in kids:
                rec(c, depth + 1)
            pos[nid] = (depth, sum(pos[c][1] for c in kids) / len(kids))

    rec(root, 0)
    return pos, max_depth[0], counter[0]


def main():
    ap = argparse.ArgumentParser(description="思维导图确定性预览渲染器")
    ap.add_argument("--map", required=True, help="输入 mindmap.json 路径")
    ap.add_argument("--outdir", required=True, help="输出目录")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    root, nodes, children, relations = load_map(args.map)
    manifest_path = os.path.join(args.outdir, "render_manifest.json")

    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import font_manager, pyplot as plt
        from matplotlib.patches import FancyArrowPatch
    except ImportError:
        m = base_manifest(nodes, relations)
        m["status"] = "skipped_no_matplotlib"
        write_manifest(manifest_path, **m)
        sys.stdout.write("matplotlib 不可用：已写入 render_manifest.json"
                         "（status=skipped_no_matplotlib）。\n")
        return 0

    # ---- CJK 字体发现 ------------------------------------------------
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((c for c in CJK_CANDIDATES if c in available), None)
    font_fallback = chosen is None
    if chosen:
        matplotlib.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
        matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["axes.unicode_minus"] = False

    # ---- 布局 ---------------------------------------------------------
    pos, max_depth, n_leaves = compute_layout(root, nodes, children)
    max_label_len = max(len(str(n["label"])) for n in nodes.values())
    spacing = max(3.0, 0.32 * max_label_len + 2.0)

    def xy(nid):
        d, y = pos[nid]
        return d * spacing, y

    width_in = max(8.0, (max_depth + 1) * spacing * 0.55 + 3.0)
    height_in = max(5.0, (n_leaves + 1) * 0.95 + 1.5)
    fig = plt.figure(figsize=(width_in, height_in))
    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
    ax.axis("off")

    # ---- 肘形连接线 ---------------------------------------------------
    for n in nodes.values():
        pid = n.get("parent")
        if pid is None:
            continue
        px, py = xy(pid)
        cx, cy = xy(n["id"])
        mx = (px + cx) / 2.0
        ax.plot([px, mx, mx, cx], [py, py, cy, cy],
                color="#888888", linewidth=1.0, zorder=1)

    # ---- 关系弧线（红色虚线 + 弧顶类型标注） -----------------------------
    # 弧度按确定性规则自适应：按 (0.3, 0.55, 0.8, 1.05) × (+, -) 的顺序
    # 枚举候选曲率与凸向，采样弧线并计算其到非端点节点椭圆包围盒的最小
    # 净距，选取首个净距 ≥ 0.3 的候选；均不满足时取净距最大者。
    # 由此避免弧线压过位于弦上的中间节点，且同一输入结果恒定。
    RAD_CANDIDATES = (0.3, 0.55, 0.8, 1.05)
    MARGIN_MIN = 0.3

    def bezier(p1, c, p2, t):
        return ((1 - t) ** 2 * p1[0] + 2 * (1 - t) * t * c[0] + t * t * p2[0],
                (1 - t) ** 2 * p1[1] + 2 * (1 - t) * t * c[1] + t * t * p2[1])

    def node_half(nid):
        # 节点底框近似半宽/半高（数据坐标单位）
        return 0.12 * len(str(nodes[nid]["label"])) + 0.35, 0.4

    for r in relations:
        x1, y1 = xy(r["from"])
        x2, y2 = xy(r["to"])
        dx, dy = x2 - x1, y2 - y1
        # matplotlib arc3 约定：控制点 = 弦中点 + rad * (dy, -dx)
        px, py = dy, -dx
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        others = [nid for nid in nodes if nid not in (r["from"], r["to"])]

        def clearance(rad):
            c = (mx + rad * px, my + rad * py)
            best = float("inf")
            for t in (0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9):
                bx, by = bezier((x1, y1), c, (x2, y2), t)
                for nid in others:
                    ox, oy = xy(nid)
                    hx, hy = node_half(nid)
                    ex = max(abs(bx - ox) - hx, 0.0)
                    ey = max(abs(by - oy) - hy, 0.0)
                    best = min(best, (ex * ex + ey * ey) ** 0.5)
            return best

        rad = None
        best_rad, best_clear = RAD_CANDIDATES[0], -1.0
        for rad_abs in RAD_CANDIDATES:
            for sign in (1.0, -1.0):
                cl = clearance(sign * rad_abs)
                if cl > best_clear:
                    best_clear = cl
                    best_rad = sign * rad_abs
                if cl >= MARGIN_MIN:
                    rad = sign * rad_abs
                    break
            if rad is not None:
                break
        if rad is None:
            rad = best_rad
        ctrl = (mx + rad * px, my + rad * py)
        patch = FancyArrowPatch(
            (x1, y1), (x2, y2),
            connectionstyle="arc3,rad=%.2f" % rad,
            arrowstyle="-|>", mutation_scale=12,
            linestyle="--", color="#cc2222", linewidth=1.2,
            alpha=0.85, zorder=2)
        ax.add_patch(patch)
        label = r.get("type", "")
        if label:
            # 标注置于弧线顶点（二次贝塞尔 t=0.5 处）沿凸向稍外侧，
            # 白底、zorder 高于节点底框，保证不被遮挡。
            ax_, ay_ = bezier((x1, y1), ctrl, (x2, y2), 0.5)
            ox, oy = ctrl[0] - mx, ctrl[1] - my
            onorm = max((ox * ox + oy * oy) ** 0.5, 1e-9)
            ax.text(ax_ + ox / onorm * 0.3, ay_ + oy / onorm * 0.3, label,
                    ha="center", va="center", fontsize=8,
                    color="#cc2222", zorder=5,
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                              edgecolor="none", alpha=0.85))

    # ---- 节点文本 -----------------------------------------------------
    for nid, n in nodes.items():
        x, y = xy(nid)
        is_root = (nid == root)
        ax.text(x, y, str(n["label"]), ha="center", va="center",
                fontsize=10 if is_root else 9,
                zorder=4,
                bbox=dict(boxstyle="round,pad=0.35",
                          facecolor="#fdeccb" if is_root else "#eef4ff",
                          edgecolor="#b08900" if is_root else "#3355aa",
                          linewidth=1.2))

    # ---- 画布范围（留白，避免裁剪） ------------------------------------
    xs = [xy(nid)[0] for nid in nodes]
    ys = [xy(nid)[1] for nid in nodes]
    ax.set_xlim(min(xs) - spacing * 0.75, max(xs) + spacing * 0.75)
    ax.set_ylim(min(ys) - 1.2, max(ys) + 1.2)

    png_path = os.path.join(args.outdir, "mindmap.png")
    pdf_path = os.path.join(args.outdir, "mindmap.pdf")
    fig.savefig(png_path, dpi=DPI)
    # 去除 PDF 创建时间元数据，保证同环境重跑字节一致
    fig.savefig(pdf_path, metadata={"CreationDate": None})
    plt.close(fig)

    m = base_manifest(nodes, relations)
    m["tool_versions"]["matplotlib"] = matplotlib.__version__
    m["font"]["chosen"] = chosen
    m["font"]["fallback"] = font_fallback
    m["canvas"] = {"width_px": int(round(width_in * DPI)),
                   "height_px": int(round(height_in * DPI))}
    m["status"] = "rendered"
    write_manifest(manifest_path, **m)
    sys.stdout.write("已渲染 mindmap.png / mindmap.pdf（字体：%s）。\n"
                     % (chosen or "未找到 CJK 字体，使用默认字体"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
