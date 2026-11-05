-- S15P31A306-326: 공백 무시 제품명 검색 키 기반.
-- 기존 products 데이터는 읽어 파생 키를 채우며, 새 제품 데이터는 만들지 않는다.
-- 생성 컬럼으로 두어 구버전 앱과 기존 샘플 SQL의 쓰기도 자동 반영한다.

BEGIN;

ALTER TABLE products
    ADD COLUMN name_compact varchar(400)
    GENERATED ALWAYS AS (replace(name_normalized, ' ', '')) STORED;

CREATE INDEX idx_products_type_brand_name_compact
    ON products (type_code, brand_normalized, name_compact);

COMMIT;
