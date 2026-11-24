#!/usr/bin/env bash
# 合成示例：演示 tribunal_validate.py 的「通过」与「拦截」两种结局。
# 用法: bash examples/run_example.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${HERE}/.." && pwd)"
VALIDATOR="${SKILL_DIR}/scripts/tribunal_validate.py"
GOOD="${HERE}/adjudication_log.jsonl"
BAD="${HERE}/expected_output/broken_log.jsonl"

echo "== 1/2 校验有效裁决日志: ${GOOD}"
python3 "${VALIDATOR}" "${GOOD}"
good_rc=$?
if [ "${good_rc}" -ne 0 ]; then
  echo "!! 有效日志未通过校验 (exit ${good_rc})，示例失败" >&2
  exit 1
fi

echo
echo "== 2/2 校验蓄意破坏的日志: ${BAD}（期望校验失败）"
python3 "${VALIDATOR}" "${BAD}"
bad_rc=$?
if [ "${bad_rc}" -eq 0 ]; then
  echo "!! 破坏日志竟然通过校验，校验门失效，示例失败" >&2
  exit 1
fi
echo
echo "破坏日志被正确拦截 (exit ${bad_rc})"
echo "示例运行完成：有效日志通过、破坏日志被拒。"
