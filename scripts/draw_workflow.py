"""Draw a crisp, minimal, conceptual 5-stage workflow diagram of the Text2Cypher Agent (matplotlib)."""
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "agent_workflow.png"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def draw_node(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    desc: str = "",
    fc: str = "#ffffff",
    ec: str = "#334155",
    tag: str = "",
    tag_fc: str = "#4f46e5",
    title_color: str = "#0f172a",
    desc_color: str = "#475569",
    lw: float = 1.6,
    radius: float = 0.22,
    zorder: int = 3,
):
    shadow = FancyBboxPatch(
        (x + 0.04, y - 0.05),
        w,
        h,
        boxstyle=f"round,pad=0.02,rounding_size={radius}",
        facecolor="#cbd5e1",
        edgecolor="none",
        alpha=0.30,
        zorder=zorder - 1,
    )
    ax.add_patch(shadow)

    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.02,rounding_size={radius}",
        facecolor=fc,
        edgecolor=ec,
        linewidth=lw,
        zorder=zorder,
    )
    ax.add_patch(box)

    if tag:
        tw = max(0.68, len(tag) * 0.145 + 0.24)
        th = 0.30
        tx = x + 0.16
        ty = y + h - th / 2 - 0.01
        tp = FancyBboxPatch(
            (tx, ty),
            tw,
            th,
            boxstyle="round,pad=0.01,rounding_size=0.12",
            facecolor=tag_fc,
            edgecolor="none",
            zorder=zorder + 2,
        )
        ax.add_patch(tp)
        ax.text(
            tx + tw / 2,
            ty + th / 2,
            tag,
            ha="center",
            va="center",
            fontsize=8.2,
            fontweight="bold",
            color="#ffffff",
            zorder=zorder + 3,
        )

    cx = x + w / 2
    if desc:
        ax.text(cx, y + h * 0.62, title, ha="center", va="center", fontsize=11.0, fontweight="bold", color=title_color, zorder=zorder + 1)
        ax.text(cx, y + h * 0.28, desc, ha="center", va="center", fontsize=8.8, color=desc_color, linespacing=1.35, zorder=zorder + 1)
    else:
        ax.text(cx, y + h / 2, title, ha="center", va="center", fontsize=11.0, fontweight="bold", color=title_color, zorder=zorder + 1)


def draw_arrow(
    ax,
    p1: tuple[float, float],
    p2: tuple[float, float],
    color: str = "#64748b",
    lw: float = 1.6,
    rad: float = 0.0,
    ls: str = "-",
    label: str = "",
    label_pos: tuple[float, float] | None = None,
):
    arr = FancyArrowPatch(
        p1,
        p2,
        arrowstyle="-|>,head_length=6.5,head_width=4.0",
        connectionstyle=f"arc3,rad={rad}",
        color=color,
        linewidth=lw,
        linestyle=ls,
        zorder=4,
    )
    ax.add_patch(arr)
    if label:
        lx, ly = label_pos if label_pos else ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        ax.text(
            lx,
            ly,
            label,
            ha="center",
            va="center",
            fontsize=8.4,
            fontweight="bold",
            color=color,
            bbox=dict(boxstyle="round,pad=0.20", facecolor="#ffffff", edgecolor=color, linewidth=0.85, alpha=0.96),
            zorder=6,
        )


def main():
    plt.rcParams["font.sans-serif"] = ["Hiragino Sans GB", "Heiti SC", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(14.0, 8.2), dpi=300)
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#f8fafc")
    ax.set_xlim(0, 14.4)
    ax.set_ylim(0, 8.5)
    ax.axis("off")

    ax.text(7.2, 8.05, "代码图谱 Text2Cypher 智能体执行流程", ha="center", va="center", fontsize=16.5, fontweight="bold", color="#0f172a")

    # ==================== Row 1: Semantic Planning & Grounding ====================
    draw_node(
        ax, 0.45, 6.20, 2.75, 1.18,
        title="自然语言问题",
        desc="用户输入代码图谱问题",
        fc="#ffffff", ec="#475569", tag="输入", tag_fc="#475569",
    )

    draw_node(
        ax, 3.85, 6.20, 5.10, 1.18,
        title="大模型语义评估与规划",
        desc="评估意图与难度 · 抽取语义实体候选 · 选择领域技能\n决定 Schema 展开范围与是否拆分为多子查询",
        fc="#faf5ff", ec="#9333ea", tag="阶段 1", tag_fc="#9333ea",
    )

    draw_node(
        ax, 9.60, 6.20, 4.35, 1.18,
        title="Schema 装配与实库对齐",
        desc="按语义标志装配实时 Schema\nNeo4j 探针核实实体真名 + 召回参考示例",
        fc="#eef2ff", ec="#4f46e5", tag="阶段 2", tag_fc="#4f46e5",
    )

    draw_arrow(ax, (3.23, 6.79), (3.82, 6.79), color="#9333ea")
    draw_arrow(ax, (8.98, 6.79), (9.57, 6.79), color="#4f46e5")

    # ==================== Row 2: Closed-Loop Execution ====================
    loop_frame = FancyBboxPatch(
        (0.45, 2.45),
        13.50,
        2.95,
        boxstyle="round,pad=0.04,rounding_size=0.28",
        facecolor="#ffffff",
        edgecolor="#0d9488",
        linewidth=1.5,
        linestyle="--",
        zorder=1,
    )
    ax.add_patch(loop_frame)
    ax.text(0.80, 5.13, "阶段 3：Cypher 生成 · 校验 · 执行自修正闭环", ha="left", va="center", fontsize=10.0, fontweight="bold", color="#0f766e", zorder=2)

    draw_arrow(ax, (10.55, 6.17), (10.55, 5.44), color="#0284c7", label="简单 / 中等 / 单路径", label_pos=(9.20, 5.80))
    draw_arrow(ax, (12.65, 6.17), (12.65, 5.44), color="#9333ea", label="复杂拆分 (多子查询)", label_pos=(12.65, 5.80))

    draw_node(
        ax, 0.90, 3.60, 3.35, 1.15,
        title="Cypher 生成",
        desc="注入 Schema · 实体 · 示例\n生成只读图查询语句",
        fc="#f0fdfa", ec="#0d9488", tag="3.1", tag_fc="#0d9488",
    )

    draw_node(
        ax, 5.52, 3.60, 3.35, 1.15,
        title="多级合法性校验",
        desc="只读安全 · Schema 预检\nEXPLAIN 语法计划校验",
        fc="#fffbeb", ec="#d97706", tag="3.2", tag_fc="#d97706",
    )

    draw_node(
        ax, 10.15, 3.60, 3.35, 1.15,
        title="图谱只读执行",
        desc="受控执行查询\n提取结果表与图拓扑",
        fc="#ecfdf5", ec="#059669", tag="3.3", tag_fc="#059669",
    )

    draw_arrow(ax, (4.28, 4.18), (5.49, 4.18), color="#0d9488")
    draw_arrow(ax, (8.90, 4.18), (10.12, 4.18), color="#d97706", label="通过", label_pos=(9.51, 4.48))

    draw_node(
        ax, 4.95, 2.63, 4.50, 0.64,
        title="反思自修正（校验失败 / 报错 / 异常空结果）",
        fc="#fef2f2", ec="#e11d48", title_color="#9f1239", lw=1.3, radius=0.16,
    )

    draw_arrow(ax, (7.20, 3.57), (7.20, 3.30), color="#e11d48", lw=1.4, ls="--")
    draw_arrow(ax, (11.82, 3.57), (9.48, 2.95), color="#e11d48", lw=1.4, rad=-0.14, ls="--")
    draw_arrow(ax, (4.92, 2.95), (2.58, 3.57), color="#e11d48", lw=1.45, rad=-0.14, ls="--")
    ax.text(3.25, 2.75, "反馈重写", ha="center", va="center", fontsize=8.2, color="#be123c", fontweight="bold", zorder=6)
    ax.text(11.15, 2.75, "异常诊断", ha="center", va="center", fontsize=8.2, color="#be123c", fontweight="bold", zorder=6)

    # ==================== Row 3: Merge & Output ====================
    draw_node(
        ax, 0.45, 0.55, 3.95, 1.18,
        title="多子图归并去重",
        desc="按节点 ID 合并多子查询结果\n去重并区分同步 / 异步依赖",
        fc="#f5f3ff", ec="#7c3aed", tag="阶段 4", tag_fc="#7c3aed",
    )

    draw_node(
        ax, 5.22, 0.55, 3.95, 1.18,
        title="自然语言总结",
        desc="基于实库返回数据生成结论\n输出结构化洞察与链路归纳",
        fc="#ecfdf5", ec="#059669", tag="阶段 5", tag_fc="#059669",
    )

    draw_node(
        ax, 10.00, 0.55, 3.95, 1.18,
        title="结果呈现与追溯",
        desc="拓扑图 · 结果表 · Cypher\n全过程追溯与报告导出",
        fc="#eff6ff", ec="#2563eb", tag="输出", tag_fc="#2563eb",
    )

    draw_arrow(ax, (2.42, 2.42), (2.42, 1.76), color="#7c3aed", label="多子查询", label_pos=(3.30, 2.09))
    draw_arrow(ax, (7.20, 2.42), (7.20, 1.76), color="#059669", label="单查询直出", label_pos=(8.20, 2.09))

    draw_arrow(ax, (4.43, 1.14), (5.19, 1.14), color="#7c3aed")
    draw_arrow(ax, (9.20, 1.14), (9.97, 1.14), color="#2563eb")

    plt.tight_layout(pad=0.35)
    fig.savefig(OUT_PATH, dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Saved 5-stage workflow diagram to {OUT_PATH}")


if __name__ == "__main__":
    main()
