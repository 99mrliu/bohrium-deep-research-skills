# 变更台账（change ledger）【SYNTHETIC 合成示例】

- case_id: SYNTH-INCREMENTAL-001
- 版本: v1 → v2（基线封存不改写，所有变更为追加式）
- 操作统计: {'MERGE': 1, 'ADD': 5, 'KEEP_DISTINCT': 1, 'UPDATE_EVIDENCE': 1, 'CONFLICT': 1}

## seq 1 · MERGE → n_mat_29a6b6b9
- 依据/理由: p2.001 显式给出全称与缩写的同一指称：'an LFP/C composite (LiFePO4/C, hereafter LFP/C)'，属同一材料的真别名；非通用术语同名。
- 被吸收别名: LFP/C（幸存者保留原 ID，别名与证据追加，不删除记录）
- 证据 [secondary/p2.001]: "an LFP/C composite (LiFePO4/C, hereafter LFP/C)"

## seq 2 · ADD → n_mtd_fcdbf779
- 证据 [secondary/p2.001]: "by a hydrothermal method"

## seq 3 · ADD → e_syn_aa16e708
- 证据 [secondary/p2.001]: "We synthesize an LFP/C composite (LiFePO4/C, hereafter LFP/C) by a hydrothermal method"

## seq 4 · KEEP_DISTINCT → n_mat_bbb0bb6d_2
- 依据/理由: 'commercial carbon black' 是通用商品材料术语：p1.003 用作碳源、p2.002 用作导电添加剂，两篇均无批号/供应商信息，无证据表明是同一物理样品，故保持区分不合并。
- 与 n_mat_bbb0bb6d 保持区分（同名/通用术语不强制合并）
- 证据 [secondary/p2.002]: "Commercial carbon black was added as a conductive additive"

## seq 5 · ADD → e_use_4e1dc752
- 证据 [secondary/p2.002]: "Commercial carbon black was added as a conductive additive during electrode fabrication"

## seq 6 · ADD → e_del_8049e38e
- 证据 [secondary/p2.003]: "The LFP/C electrode delivered 149 mAh/g at 0.1 C"

## seq 7 · UPDATE_EVIDENCE → n_mtr_7c1cd688
- 证据 [primary/p1.004]: "At 0.1 C the composite delivered 158 mAh/g"

## seq 8 · ADD → n_mat_d3d8d3bf
- 证据 [secondary/p2.004]: "sol-gel derived powders"

## seq 9 · CONFLICT → e_out_a6c00e17
- 依据/理由: p1.004 称溶胶凝胶 LiFePO4/C 优于水热参比样品（158 vs 141 mAh/g，0.1 C）；p2.004 称水热 LFP/C 倍率性能高于溶胶凝胶粉体。两篇结论方向相反，且样品、方法与测试条件不同，不可合并为单一结论，双方并列保留。
- 与 e_out_bc8f5646 冲突，conflict_group=cf_b39462fd；两条边都保留，均未覆盖
- 证据 [secondary/p2.004]: "our hydrothermal LFP/C shows higher rate capability than sol-gel derived powders"

## 当前图规模
- 节点 9，边 9（含 conflicted 状态边，双方证据并列保留）
