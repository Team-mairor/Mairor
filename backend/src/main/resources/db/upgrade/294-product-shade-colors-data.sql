-- 옛 대표 색(product_shades.color_*)을 색 칸(product_shade_colors)으로 옮긴다 (S15P31A306-294).
-- 294-product-shade-colors.sql 을 먼저 적용한 DB 에서, 옮길 값이 있을 때만 적용한다.
--
-- 먼저 옮길 값이 있는지 센다. 0 이면 이 파일은 필요 없다.
--   SELECT count(*) FROM product_shades WHERE color_hex IS NOT NULL;
--
-- 호수마다 칸 1개를 만들고, 이미 칸이 있는 호수는 건드리지 않아서 다시 적용해도 된다.
-- 옛 color_source 는 값 범위가 정해진 적이 없어서 칸의 허용 출처에 없는 값은 가장 낮은 우선순위(SAMPLE)로 옮긴다.
-- 그래서 이후 수집이 쓸 수 있는 색을 얻으면 교체한다. 옛 값은 자동 승인(AUTO_APPROVED)으로 옮겨 그대로 서비스에 쓴다.
-- 적용 뒤에도 옛 컬럼은 지우지 않는다 (파우치 등록이 전환되기 전까지 읽는다).

BEGIN;

INSERT INTO product_shade_colors (id, shade_id, sort_order, name, name_normalized, name_source,
                                  color_hex, color_source, color_estimated, review_status, created_at, updated_at)
SELECT gen_random_uuid(), s.id, 1, NULL, NULL, 'NONE', s.color_hex,
       CASE WHEN s.color_source IN ('SOURCE_VALUE', 'SWATCH_CHIP', 'PRODUCT_PHOTO', 'WEB_PHOTO', 'LLM_ESTIMATE', 'SAMPLE')
            THEN s.color_source ELSE 'SAMPLE' END,
       s.color_estimated, 'AUTO_APPROVED', now(), now()
FROM product_shades s
WHERE s.color_hex IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM product_shade_colors c WHERE c.shade_id = s.id);

COMMIT;
