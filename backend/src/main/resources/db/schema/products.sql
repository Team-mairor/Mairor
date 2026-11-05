-- 화장품 카탈로그 (S15P31A306-209). 엔티티: products/entity/*.java
--
-- 운영 프로파일은 ddl-auto=validate 라서 이 테이블들이 먼저 있어야 앱이 기동한다.
-- 빈 DB 에만 적용한다. 이미 테이블이 있는 DB 에 다시 적용하면 already exists 로 실패한다.
-- 적용 순서: users.sql → products.sql → db/seed/product-categories.sql → (개발 환경만) db/seed/dev/product-samples.sql
-- Flyway 를 도입하면 db/migration/V<번호>__create_products.sql 로 옮긴다. 번호는 Flyway 담당과 확인한다.
--
-- 제약·인덱스 이름은 엔티티 상수와 같아야 하고, ProductsSchemaSqlTest 가 이름과 컬럼 순서를 확인한다.
--
-- 정규화 컬럼(*_normalized)은 CatalogTextNormalizer 로 계산한 비교용 키다. 트리거가 없으므로 SQL 로 직접 넣을 때도
-- 같은 규칙으로 계산한 값을 넣어야 한다. 크롤링 적재는 엔티티를 거쳐 저장한다.
--
-- 앱에서만 지키는 규칙 (DB 가 막지 않는다):
--   shade_selectable=false 카테고리의 제품에는 호수를 연결하지 않는다 (Product.addShade). SQL 로 직접 넣으면 막지 못한다.

-- 카테고리 9개. 값은 db/seed/product-categories.sql 로만 넣는다.
CREATE TABLE product_categories (
    code             varchar(20) NOT NULL,
    label            varchar(50) NOT NULL,
    matchable        boolean     NOT NULL,
    shade_selectable boolean     NOT NULL,
    sort_order       integer     NOT NULL,
    CONSTRAINT product_categories_pkey PRIMARY KEY (code)
);

-- 카테고리별 종류. 코드명은 기능명세 POUCH-004 라벨을 옮긴 초안이다. TODO(확인 필요 2)
-- uk_product_types_category_code 는 products 의 (category_code, type_code) 복합 FK 가 참조한다.
CREATE TABLE product_types (
    code          varchar(40) NOT NULL,
    category_code varchar(20) NOT NULL,
    label         varchar(50) NOT NULL,
    sort_order    integer     NOT NULL,
    CONSTRAINT product_types_pkey PRIMARY KEY (code),
    CONSTRAINT fk_product_types_category FOREIGN KEY (category_code) REFERENCES product_categories (code),
    CONSTRAINT uk_product_types_category_code UNIQUE (category_code, code)
);
CREATE INDEX idx_product_types_category_order ON product_types (category_code, sort_order);

-- 카테고리별 호환 부위. 부위 코드가 정해지지 않아 비워 두고, API 는 빈 목록을 응답한다. TODO(확인 필요 2)
CREATE TABLE product_category_parts (
    category_code varchar(20) NOT NULL,
    part_code     varchar(30) NOT NULL,
    CONSTRAINT product_category_parts_pkey PRIMARY KEY (category_code, part_code),
    CONSTRAINT fk_product_category_parts_category FOREIGN KEY (category_code) REFERENCES product_categories (code)
);

-- 제품. brand·name 은 원문, *_normalized 는 비교용 키(원문의 두 배 길이: 소문자화로 글자 수가 늘 수 있다).
-- source·source_product_id·source_url·collected_at 은 크롤링 출처이며 직접 넣은 데이터는 NULL 이다.
-- 카테고리와 종류가 맞지 않으면 fk_products_category_type 이 거부한다.
CREATE TABLE products (
    id                uuid                        NOT NULL,
    brand             varchar(100)                NOT NULL,
    name              varchar(200)                NOT NULL,
    brand_normalized  varchar(200)                NOT NULL,
    name_normalized   varchar(400)                NOT NULL,
    category_code     varchar(20)                 NOT NULL,
    type_code         varchar(40)                 NOT NULL,
    source            varchar(100),
    source_product_id varchar(100),
    source_url        varchar(1000),
    collected_at      timestamp(6) with time zone,
    image_url         varchar(1000),
    sale_status       varchar(20),
    created_at        timestamp(6) with time zone NOT NULL,
    updated_at        timestamp(6) with time zone NOT NULL,
    CONSTRAINT products_pkey PRIMARY KEY (id),
    CONSTRAINT fk_products_category_type FOREIGN KEY (category_code, type_code)
        REFERENCES product_types (category_code, code),
    CONSTRAINT uk_products_type_brand_name UNIQUE (type_code, brand_normalized, name_normalized),
    CONSTRAINT ck_products_sale_status CHECK (sale_status IN ('ON_SALE', 'SOLD_OUT', 'MISSING'))
);
-- 같은 출처의 같은 상품 번호는 한 제품이다 (재수집이 같은 제품을 찾는 키). 직접 넣은 데이터(source NULL)는 제외한다.
-- 부분 유니크 인덱스는 JPA 로 표현할 수 없어 SQL 에만 있다.
CREATE UNIQUE INDEX uk_products_source_product ON products (source, source_product_id) WHERE source IS NOT NULL;

-- 호수. 정렬은 sort_order, name_normalized 순이다 (제품 안에서 name_normalized 가 유니크라 순서가 하나로 정해진다).
-- 색상 세 컬럼은 모두 NULL(색상 없음)이거나 모두 값이 있어야 하고, HEX 는 #RRGGBB 대문자만 허용한다.
-- color_source 값 범위는 미정이다. TODO
CREATE TABLE product_shades (
    id              uuid                        NOT NULL,
    product_id      uuid                        NOT NULL,
    name            varchar(100)                NOT NULL,
    name_normalized varchar(200)                NOT NULL,
    sort_order      integer                     NOT NULL,
    color_hex       varchar(7),
    color_source    varchar(30),
    color_estimated boolean,
    source_option_id varchar(200),
    created_at      timestamp(6) with time zone NOT NULL,
    updated_at      timestamp(6) with time zone NOT NULL,
    CONSTRAINT product_shades_pkey PRIMARY KEY (id),
    CONSTRAINT fk_product_shades_product FOREIGN KEY (product_id) REFERENCES products (id),
    CONSTRAINT uk_product_shades_product_name UNIQUE (product_id, name_normalized),
    CONSTRAINT ck_product_shades_color_all_or_none CHECK (
        (color_hex IS NULL AND color_source IS NULL AND color_estimated IS NULL)
        OR (color_hex IS NOT NULL AND color_source IS NOT NULL AND color_estimated IS NOT NULL)),
    CONSTRAINT ck_product_shades_color_hex CHECK (color_hex ~ '^#[0-9A-F]{6}$')
);
CREATE INDEX idx_product_shades_product_order ON product_shades (product_id, sort_order, name_normalized);
-- 수집 출처가 준 옵션 값. 같은 제품 안에서 유일하다 (재수집이 같은 호수를 찾는 키). 직접 넣은 호수는 NULL.
CREATE UNIQUE INDEX uk_product_shades_source_option ON product_shades (product_id, source_option_id) WHERE source_option_id IS NOT NULL;

-- 호수가 합쳐질 때 사라지는 옵션 값. 옵션 값으로 호수를 계속 찾을 수 있게 남긴다. 같은 제품 안에서 다른 호수와 겹치는지는
-- 적재 코드가 확인한다 (DB 는 한 호수 안의 중복만 막는다).
CREATE TABLE product_shade_option_aliases (
    shade_id         uuid         NOT NULL,
    source_option_id varchar(200) NOT NULL,
    CONSTRAINT product_shade_option_aliases_pkey PRIMARY KEY (shade_id, source_option_id),
    CONSTRAINT fk_product_shade_option_aliases_shade FOREIGN KEY (shade_id) REFERENCES product_shades (id)
);

-- 호수의 색 칸 (S15P31A306-294). 호수 하나에 칸이 0..N개이고 듀오·팔레트도 칸마다 저장한다.
-- id 는 colorId(영구 식별자)라 칸을 지우고 다시 만들지 않는다. 칸 이름은 사이트 글자나 사진에 인쇄된 이름만이고,
-- 이름이 없으면 name 은 NULL 이고 name_source 는 NONE 이다 (순서대로 센 번호는 이름이 아니다).
-- 색 컬럼 4개는 모두 NULL('색을 못 구함')이거나 모두 값이 있어야 한다. BELOW_THRESHOLD·REJECTED 는 HEX 를 남긴 채 서비스에 쓰지 않는다.
-- 칸 순서 유니크는 한 트랜잭션에서 순서를 바꿀 수 있게 DEFERRABLE 이다.
-- 앱에서만 지키는 규칙: 사진·LLM·사이트 색값 출처는 color_estimated=true 이다 (ProductShadeColor).
-- 근거(이미지·영역·방법)는 DB 에 두지 않고 수집 실행 결과 파일에 둔다. 근거 연결 컬럼은 S15P31A306-295 에서 추가한다.
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
