-- q3：语义合法但结果为空的查询（阈值高于该数据集任何物理可能取值）。
-- 正确纪律：如实记录 empty_result 与 0 行，绝不暗中放宽条件。
SELECT reading_id, site_id, ts, value
FROM readings
WHERE status = 'valid'
  AND value > 1000000;
