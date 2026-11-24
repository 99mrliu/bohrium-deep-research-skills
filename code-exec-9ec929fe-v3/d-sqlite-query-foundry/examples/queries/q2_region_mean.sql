-- q2：各区域有效读数的均值与样本数（JOIN + GROUP BY 写法）。
-- 该聚合将在 reconcile_claim.json 中以 IN 子查询写法独立复核。
SELECT s.region,
       COUNT(r.reading_id) AS n_valid,
       AVG(r.value) AS mean_value
FROM readings r
JOIN sites s ON s.site_id = r.site_id
WHERE r.status = 'valid'
  AND r.value IS NOT NULL
GROUP BY s.region
ORDER BY s.region;
