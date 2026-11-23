# Benchmarking LSM-Tree Compaction Strategies for Time-Series Storage

Synthetic Systems Lab. This document is a synthetic example for skill demonstration only and does not describe real experiments.

We study leveled and tiered compaction policies in an LSM-tree key-value store ingesting append-only sensor workloads at steady state.

Our harness replays a synthetic zipfian write stream of 200 million keys on NVMe storage and records p50 and p99 query latency plus sustained write throughput in ops per second.

Leveled compaction reaches a p99 lookup latency of 42 ms with a write amplification of 11.3, while tiered compaction keeps write amplification at 4.6 but raises p99 latency to 87 ms.

Memory budget per node was fixed at 16 GB and block cache size at 4 GB across all runs.

We conclude that workload skew, not raw device bandwidth, dominates the latency-amplification trade-off for this class of stores.
