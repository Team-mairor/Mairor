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
-- 내용: 립틴트 1개(호수 3개: 색상 있음 2, 없음 1), 토너 1개(호수 없음).

INSERT INTO products (id, brand, name, brand_normalized, name_normalized, category_code, type_code,
                      created_at, updated_at) VALUES
    ('00000000-0000-4000-8000-000000000101', 'Mairor Sample', 'Water Gel Tint',
     'mairor sample', 'water gel tint', 'LIP', 'LIP_TINT', now(), now()),
    ('00000000-0000-4000-8000-000000000102', 'Mairor Sample', 'Daily Toner',
     'mairor sample', 'daily toner', 'SKINCARE', 'TONER', now(), now())
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
     '03 Nude', '03 nude', 3, NULL, NULL, NULL, now(), now())
ON CONFLICT (id) DO UPDATE SET
    product_id      = EXCLUDED.product_id,
    name            = EXCLUDED.name,
    name_normalized = EXCLUDED.name_normalized,
    sort_order      = EXCLUDED.sort_order,
    color_hex       = EXCLUDED.color_hex,
    color_source    = EXCLUDED.color_source,
    color_estimated = EXCLUDED.color_estimated,
    updated_at      = now();
