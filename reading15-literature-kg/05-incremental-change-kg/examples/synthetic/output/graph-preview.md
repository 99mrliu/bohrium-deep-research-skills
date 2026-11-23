# 图谱预览（当前版本 v2）【SYNTHETIC 合成示例】

节点 9，边 9。每条记录的完整证据见 graph-current.json。

## 节点
| id | type | label | aliases | 证据数 |
|-|-|-|-|-|
| n_mat_29a6b6b9 | material | LiFePO4/C composite | LFP/C | 2 |
| n_mat_9f9f2e2e | material | hydrothermal reference sample |  | 1 |
| n_mat_bbb0bb6d | material | commercial carbon black |  | 1 |
| n_mat_bbb0bb6d_2 | material | commercial carbon black |  | 1 |
| n_mat_d3d8d3bf | material | sol-gel derived powders |  | 1 |
| n_mtd_8ea853ed | method | sol-gel method |  | 1 |
| n_mtd_fcdbf779 | method | hydrothermal method |  | 1 |
| n_mtr_7c1cd688 | metric | discharge capacity |  | 2 |
| n_tsk_3ff09b99 | task | lithium-ion battery cathode |  | 1 |

## 边
| id | relation | from | to | value | condition | status |
|-|-|-|-|-|-|-|
| e_app_d4952e95 | applied_to | n_mat_29a6b6b9 | n_tsk_3ff09b99 |  |  | active |
| e_del_8049e38e | delivers_capacity | n_mat_29a6b6b9 | n_mtr_7c1cd688 | 149 mAh/g | 0.1 C | active |
| e_del_c14a37e0 | delivers_capacity | n_mat_29a6b6b9 | n_mtr_7c1cd688 | 158 mAh/g | 0.1 C | active |
| e_out_a6c00e17 | outperforms | n_mat_29a6b6b9 | n_mat_d3d8d3bf |  |  | conflicted |
| e_out_bc8f5646 | outperforms | n_mat_29a6b6b9 | n_mat_9f9f2e2e | 158 vs 141 mAh/g | 0.1 C | conflicted |
| e_syn_7c5ee1ef | synthesized_by | n_mat_29a6b6b9 | n_mtd_8ea853ed |  |  | active |
| e_syn_aa16e708 | synthesized_by | n_mat_29a6b6b9 | n_mtd_fcdbf779 |  |  | active |
| e_use_4e1dc752 | uses | n_mat_29a6b6b9 | n_mat_bbb0bb6d_2 |  |  | active |
| e_use_ac3780be | uses | n_mat_29a6b6b9 | n_mat_bbb0bb6d |  |  | active |
