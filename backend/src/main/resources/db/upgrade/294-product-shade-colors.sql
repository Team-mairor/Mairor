-- 호수별 색 칸 (S15P31A306-294). 이미 products.sql 이 적용된 DB 에 변경분만 적용한다.
-- 빈 DB 에는 이 파일이 아니라 db/schema/products.sql 전체를 적용한다 (이 파일의 결과는 products.sql 과 같다).
--
-- 컬럼·테이블·인덱스를 추가하기만 해서 옛 버전 앱과 함께 돌아도 깨지지 않는다. 옛 product_shades.color_* 컬럼은 지우지 않는다.
-- 적용은 BE(정윤)가 머지 전에 한다 (deploy/README.md "DB 스키마"). 한 번만 적용한다 (이미 있으면 already exists 로 실패한다).
-- 다음에는 옛 대표 색을 색 칸으로 옮기는 294-product-shade-colors-data.sql 을 필요할 때만 적용한다.
--
-- 적용 전에 확인한다 (둘 다 0 이어야 한다).
--   1) 새 유니크 인덱스(uk_products_source_product)를 막는 중복. 있으면 이 파일 전체가 롤백된다.
--      SELECT source, source_product_id, count(*) FROM products WHERE source IS NOT NULL GROUP BY 1, 2 HAVING count(*) > 1;
--   2) 옮길 옛 대표 색. 0 이 아니면 이 파일 다음에 294-product-shade-colors-data.sql 도 같은 시점에 적용한다.
--      검색 응답은 이제 product_shade_colors 만 읽어서, 이관하지 않으면 그 호수의 colors 가 빈 목록으로 나온다.
--      SELECT count(*) FROM product_shades WHERE color_hex IS NOT NULL;

BEGIN;

ALTER TABLE products
    ADD COLUMN image_url   varchar(1000),
    ADD COLUMN sale_status varchar(20),
    ALTER COLUMN source TYPE varchar(100),
    ADD CONSTRAINT ck_products_sale_status CHECK (sale_status IN ('ON_SALE', 'SOLD_OUT', 'MISSING'));
CREATE UNIQUE INDEX uk_products_source_product ON products (source, source_product_id) WHERE source IS NOT NULL;

ALTER TABLE product_shades ADD COLUMN source_option_id varchar(200);
CREATE UNIQUE INDEX uk_product_shades_source_option ON product_shades (product_id, source_option_id) WHERE source_option_id IS NOT NULL;

CREATE TABLE product_shade_option_aliases (
    shade_id         uuid         NOT NULL,
    source_option_id varchar(200) NOT NULL,
    CONSTRAINT product_shade_option_aliases_pkey PRIMARY KEY (shade_id, source_option_id),
    CONSTRAINT fk_product_shade_option_aliases_shade FOREIGN KEY (shade_id) REFERENCES product_shades (id)
);

CREATE TABLE product_shade_colors (
    id                  uuid                        NOT NULL,
    shade_id            uuid                        NOT NULL,
    sort_order          integer                     NOT NULL,
    name                varchar(100),
    name_normalized     varchar(200),
    name_source         varchar(20)                 NOT NULL,
    color_hex           varchar(7),
    color_source        varchar(30),
    color_estimated     boolean,
    review_status       varchar(20),
    source_collected_at timestamp(6) with time zone,
    created_at          timestamp(6) with time zone NOT NULL,
    updated_at          timestamp(6) with time zone NOT NULL,
    CONSTRAINT product_shade_colors_pkey PRIMARY KEY (id),
    CONSTRAINT fk_product_shade_colors_shade FOREIGN KEY (shade_id) REFERENCES product_shades (id),
    CONSTRAINT uk_product_shade_colors_shade_order UNIQUE (shade_id, sort_order) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT ck_product_shade_colors_name_pair CHECK ((name IS NULL) = (name_normalized IS NULL)),
    CONSTRAINT ck_product_shade_colors_name_source CHECK (
        (name IS NULL AND name_source = 'NONE')
        OR (name IS NOT NULL AND name_source IN ('SITE_TEXT', 'IMAGE_PRINT'))),
    CONSTRAINT ck_product_shade_colors_all_or_none CHECK (
        (color_hex IS NULL AND color_source IS NULL AND color_estimated IS NULL AND review_status IS NULL)
        OR (color_hex IS NOT NULL AND color_source IS NOT NULL AND color_estimated IS NOT NULL
            AND review_status IS NOT NULL)),
    CONSTRAINT ck_product_shade_colors_hex CHECK (color_hex ~ '^#[0-9A-F]{6}$'),
    CONSTRAINT ck_product_shade_colors_source CHECK (
        color_source IN ('SOURCE_VALUE', 'SWATCH_CHIP', 'PRODUCT_PHOTO', 'WEB_PHOTO', 'LLM_ESTIMATE', 'SAMPLE')),
    CONSTRAINT ck_product_shade_colors_review CHECK (
        review_status IN ('AUTO_APPROVED', 'BELOW_THRESHOLD', 'APPROVED', 'REJECTED'))
);
CREATE INDEX idx_product_shade_colors_shade_order ON product_shade_colors (shade_id, sort_order);

COMMIT;
