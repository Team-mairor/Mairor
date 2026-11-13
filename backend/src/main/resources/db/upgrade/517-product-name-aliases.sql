-- 회원이 쓴 제품 이름의 별칭 (S15P31A306-517). 517-catalog-collect-requests.sql 다음에 따로 적용한다
-- (517 SQL 은 운영 DB 에 이미 적용했다). 빈 DB 에는 이 파일이 아니라 db/schema/products.sql 전체를 적용한다(결과가 같다).
--
-- 새 테이블 하나와 인덱스만 더해서 옛 버전 앱과 함께 돌아도 깨지지 않는다. 새 버전 배포(ddl-auto=validate) 전에 적용한다.
-- 한 번만 적용한다(이미 있으면 already exists 로 실패하고 전체가 롤백된다).
--
-- 적용 전에 확인한다: SELECT to_regclass('product_name_aliases');  -- NULL 이어야 한다
-- 적용 후에 확인한다: SELECT count(*) FROM product_name_aliases;    -- 0

BEGIN;
CREATE TABLE product_name_aliases (
    id               uuid                        NOT NULL,
    type_code        varchar(40)                 NOT NULL,
    brand_normalized varchar(200)                NOT NULL,
    name_compact     varchar(400)                NOT NULL,
    product_id       uuid                        NOT NULL,
    request_id       uuid,
    created_at       timestamp(6) with time zone NOT NULL,
    CONSTRAINT product_name_aliases_pkey PRIMARY KEY (id),
    CONSTRAINT fk_product_name_aliases_product FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
    CONSTRAINT uk_product_name_aliases_key UNIQUE (type_code, brand_normalized, name_compact),
    CONSTRAINT ck_product_name_aliases_nonempty CHECK (brand_normalized <> '' AND name_compact <> '')
);
CREATE INDEX idx_product_name_aliases_product ON product_name_aliases (product_id);

COMMIT;
