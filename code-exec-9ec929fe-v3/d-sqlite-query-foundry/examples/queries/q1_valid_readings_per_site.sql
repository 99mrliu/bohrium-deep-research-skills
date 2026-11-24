-- q1：各站点有效读数行数（LEFT JOIN 保留无读数的站点，其计数为 0）。
-- 注意：本查询刻意不做去重，重复批次会被计入，
--       供 reconcile_claim.json 的第 3 项检查演示如何把重复暴露出来。
SELECT s.site_id,
       s.region,
       COUNT(r.reading_id) AS valid_readings
FROM sites s
LEFT JOIN readings r
       ON r.site_id = s.site_id
      AND r.status = 'valid'
      AND r.value IS NOT NULL
GROUP BY s.site_id, s.region
ORDER BY s.site_id;
