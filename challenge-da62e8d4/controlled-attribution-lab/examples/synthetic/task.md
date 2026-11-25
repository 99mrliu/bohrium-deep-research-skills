# Synthetic task

The material gives a target integral and a pre-registered absolute-error tolerance
of 0.02. Candidate A uses left-rectangle quadrature and currently misses the
target tolerance. Candidate B is an independent Simpson implementation and must
still be run even if A fails.

Before viewing intervention outcomes, seal `plan.json`. 通过一次只改
`parameter.steps` 的干预检验 A 的参数 bug；另设一个预期会因反向效应而
falsified 的方向假设，以及 B 的 seed/noise-floor inconclusive 假设。比较每次
运行的 target/error/tolerance 字段，保留全部 stdout/stderr 与审计记录。

This is not a formal PDF reproduction: there is no real PDF and no original data
repository in this synthetic example. Parameters not present in the material are
experiment-defined. The formal workflow and required PDF/figure comparisons are
specified in `SKILL.md`; the example tests the intervention mechanism only.
