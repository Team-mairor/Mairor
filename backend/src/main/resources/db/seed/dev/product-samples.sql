-- 개발 전용 샘플 제품·호수 (S15P31A306-209). 운영 DB 에는 적용하지 않는다.
--
-- 적용 순서: db/schema/products.sql → db/seed/product-categories.sql 다음. 여러 번 적용해도 된다.
--   - 모든 행은 고정 UUID 이고, 같은 id 가 있으면 이 파일의 값으로 갱신한다 (샘플을 고친 뒤 다시 적용하면 반영된다).
--   - 다른 id 로 정규화 키가 같은 제품·호수가 이미 있으면 유니크 제약으로 실패한다. 개발 DB 에서만 생기는 경우라 그대로 둔다.
--
-- 브랜드·제품명은 실제 제품이 아닌 설명용 값이다.
-- *_normalized 는 CatalogTextNormalizer 규칙(NFC → 공백 축약 → 앞뒤 공백 제거 → 소문자화)으로 계산한 값이다.
-- 원문을 고치면 정규화 값도 같이 고친다. 어긋나면 ProductSeedSqlTest 가 실패한다.
--
-- 내용: 립틴트 1개(호수 3개: 색상 있음 2, 없음 1), 토너 1개(호수 없음), 아이섀도 팔레트 1개(호수 1개, 색 칸 3개:
--       사용 가능 1, 품질 미달 1, 색 없음 1).
-- 호수의 옛 대표 색상(product_shades.color_*)과 새 색 칸(product_shade_colors)에 같은 색을 넣는다. 옛 컬럼은 제거 전까지 남아 있다.

INSERT INTO products (id, brand, name, brand_normalized, name_normalized, category_code, type_code,
                      created_at, updated_at) VALUES
    ('00000000-0000-4000-8000-000000000101', 'Mairor Sample', 'Water Gel Tint',
     'mairor sample', 'water gel tint', 'LIP', 'LIP_TINT', now(), now()),
    ('00000000-0000-4000-8000-000000000102', 'Mairor Sample', 'Daily Toner',
     'mairor sample', 'daily toner', 'SKINCARE', 'TONER', now(), now()),
    ('00000000-0000-4000-8000-000000000103', 'Mairor Sample', 'Three Color Palette',
     'mairor sample', 'three color palette', 'EYE', 'EYESHADOW_PALETTE', now(), now())
ON CONFLICT (id) DO UPDATE SET
    brand            = EXCLUDED.brand,
    name             = EXCLUDED.name,
    brand_normalized = EXCLUDED.brand_normalized,
    name_normalized  = EXCLUDED.name_normalized,
    category_code    = EXCLUDED.category_code,
    type_code        = EXCLUDED.type_code,
    updated_at       = now();

INSERT INTO product_shades (id, product_id, name, name_normalized, sort_order,
                            color_hex, color_source, color_estimated, created_at, updated_at) VALUES
    ('00000000-0000-4000-8000-000000000201', '00000000-0000-4000-8000-000000000101',
     '01 Coral', '01 coral', 1, '#F2665A', 'SAMPLE', false, now(), now()),
    ('00000000-0000-4000-8000-000000000202', '00000000-0000-4000-8000-000000000101',
     '02 Cherry', '02 cherry', 2, '#C8102E', 'SAMPLE', true, now(), now()),
    ('00000000-0000-4000-8000-000000000203', '00000000-0000-4000-8000-000000000101',
     '03 Nude', '03 nude', 3, NULL, NULL, NULL, now(), now()),
    ('00000000-0000-4000-8000-000000000204', '00000000-0000-4000-8000-000000000103',
     '01 Dusk', '01 dusk', 1, NULL, NULL, NULL, now(), now())
ON CONFLICT (id) DO UPDATE SET
    product_id      = EXCLUDED.product_id,
    name            = EXCLUDED.name,
    name_normalized = EXCLUDED.name_normalized,
    sort_order      = EXCLUDED.sort_order,
    color_hex       = EXCLUDED.color_hex,
    color_source    = EXCLUDED.color_source,
    color_estimated = EXCLUDED.color_estimated,
    updated_at      = now();

-- 색 칸. 팔레트(호수 204)는 칸 3개이고, 이름이 있는 칸·품질 미달로 쓰지 않는 칸·색이 없는 칸이 하나씩 있다.
INSERT INTO product_shade_colors (id, shade_id, sort_order, name, name_normalized, name_source,
                                  color_hex, color_source, color_estimated, review_status,
                                  created_at, updated_at) VALUES
    ('00000000-0000-4000-8000-000000000401', '00000000-0000-4000-8000-000000000201', 1,
     NULL, NULL, 'NONE', '#F2665A', 'SAMPLE', false, 'AUTO_APPROVED', now(), now()),
    ('00000000-0000-4000-8000-000000000402', '00000000-0000-4000-8000-000000000202', 1,
     NULL, NULL, 'NONE', '#C8102E', 'SAMPLE', true, 'AUTO_APPROVED', now(), now()),
    ('00000000-0000-4000-8000-000000000403', '00000000-0000-4000-8000-000000000203', 1,
     NULL, NULL, 'NONE', NULL, NULL, NULL, NULL, now(), now()),
    ('00000000-0000-4000-8000-000000000404', '00000000-0000-4000-8000-000000000204', 1,
     'Matte Sand', 'matte sand', 'SITE_TEXT', '#D9B8A0', 'SAMPLE', false, 'AUTO_APPROVED', now(), now()),
    ('00000000-0000-4000-8000-000000000405', '00000000-0000-4000-8000-000000000204', 2,
     'Shimmer Rose', 'shimmer rose', 'SITE_TEXT', '#B76E79', 'SAMPLE', false, 'BELOW_THRESHOLD', now(), now()),
    ('00000000-0000-4000-8000-000000000406', '00000000-0000-4000-8000-000000000204', 3,
     NULL, NULL, 'NONE', NULL, NULL, NULL, NULL, now(), now())
ON CONFLICT (id) DO UPDATE SET
    shade_id        = EXCLUDED.shade_id,
    sort_order      = EXCLUDED.sort_order,
    name            = EXCLUDED.name,
    name_normalized = EXCLUDED.name_normalized,
    name_source     = EXCLUDED.name_source,
    color_hex       = EXCLUDED.color_hex,
    color_source    = EXCLUDED.color_source,
    color_estimated = EXCLUDED.color_estimated,
    review_status   = EXCLUDED.review_status,
    updated_at      = now();
