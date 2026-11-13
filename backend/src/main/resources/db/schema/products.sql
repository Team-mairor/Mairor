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

-- 카테고리별 종류. 기준 코드는 db/seed/product-categories.sql 및 FE 파우치 계약을 따른다.
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

-- 카테고리 조회용 호환 부위 값. 현재 시드는 비어 있다. 추천 대체 호환성은 PouchCompatibilityPolicy 가 종류 코드 기준으로 관리한다.
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
    name_compact      varchar(400) GENERATED ALWAYS AS (replace(name_normalized, ' ', '')) STORED,
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
CREATE INDEX idx_products_type_brand_name_compact ON products (type_code, brand_normalized, name_compact);

-- 호수. 정렬은 sort_order, name_normalized 순이다 (제품 안에서 name_normalized 가 유니크라 순서가 하나로 정해진다).
-- 색상 세 컬럼은 모두 NULL(색상 없음)이거나 모두 값이 있어야 하고, HEX 는 #RRGGBB 대문자만 허용한다.
-- color_source 는 ColorSource enum 값(SOURCE_VALUE, SWATCH_CHIP, PRODUCT_PHOTO, WEB_PHOTO, LLM_ESTIMATE, SAMPLE)만 저장한다.
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

-- 카탈로그 적재 실행 (S15P31A306-295). 수집기가 한 번 돌린 실행 하나가 한 행이다.
-- run_id 는 수집기가 header 에 쓴 runId 이고 유니크라, 끊긴 실행을 이어서 보내도 같은 행을 쓴다.
-- result_file 은 공유 볼륨(/data/catalog-runs)의 상대 이름이다. 이미지 URL·영역·방법 같은 근거는 DB 에 두지 않고 그 파일에 둔다.
-- RUNNING 이 아니면 finished_at 이 있다. last_heartbeat_at 이 오래되면 ABANDONED 로 끝낸다.
CREATE TABLE catalog_import_runs (
    id                   uuid                        NOT NULL,
    run_id               varchar(100)                NOT NULL,
    seed                 varchar(100),
    collector_version    varchar(50),
    result_file          varchar(200),
    status               varchar(20)                 NOT NULL,
    collector_started_at timestamp(6) with time zone,
    last_heartbeat_at    timestamp(6) with time zone NOT NULL,
    finished_at          timestamp(6) with time zone,
    created_at           timestamp(6) with time zone NOT NULL,
    updated_at           timestamp(6) with time zone NOT NULL,
    CONSTRAINT catalog_import_runs_pkey PRIMARY KEY (id),
    CONSTRAINT uk_catalog_import_runs_run_id UNIQUE (run_id),
    CONSTRAINT ck_catalog_import_runs_status CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'ABANDONED')),
    CONSTRAINT ck_catalog_import_runs_finished CHECK ((status = 'RUNNING') = (finished_at IS NULL))
);
CREATE INDEX idx_catalog_import_runs_status_heartbeat ON catalog_import_runs (status, last_heartbeat_at);

-- 적재 실행의 건. 수집 상품 한 건(item_key)의 처리 결과다. (run_id, item_key) 유니크라 같은 건을 다시 보내도 한 번만 처리한다.
-- outcome 은 제품 단위 판정(NEW·UPDATE·STALE·AMBIGUOUS·UNCLASSIFIED)과 형식이 틀린 건(INVALID), 처리 중 오류가 난 건(FAILED)이다.
-- reasons 는 사유 코드를 쉼표로 이은 문자열이고 없으면 빈 문자열이다. message 는 오류 요약이며 스택 트레이스는 넣지 않는다.
-- colors_applied 는 이 건이 저장하거나 바꾼 색 칸 수다. product_id 는 반영한 제품이고 반영하지 않았으면 NULL 이다.
CREATE TABLE catalog_import_items (
    id                uuid                        NOT NULL,
    run_id            uuid                        NOT NULL,
    item_key          varchar(100)                NOT NULL,
    source            varchar(100),
    source_product_id varchar(100),
    outcome           varchar(20)                 NOT NULL,
    partial           boolean                     NOT NULL,
    reasons           varchar(1000)               NOT NULL,
    product_id        uuid,
    colors_applied    integer                     NOT NULL,
    message           varchar(500),
    created_at        timestamp(6) with time zone NOT NULL,
    updated_at        timestamp(6) with time zone NOT NULL,
    CONSTRAINT catalog_import_items_pkey PRIMARY KEY (id),
    CONSTRAINT fk_catalog_import_items_run FOREIGN KEY (run_id) REFERENCES catalog_import_runs (id),
    CONSTRAINT fk_catalog_import_items_product FOREIGN KEY (product_id) REFERENCES products (id),
    CONSTRAINT uk_catalog_import_items_run_item UNIQUE (run_id, item_key),
    CONSTRAINT ck_catalog_import_items_outcome CHECK (
        outcome IN ('NEW', 'UPDATE', 'STALE', 'AMBIGUOUS', 'UNCLASSIFIED', 'INVALID', 'FAILED')),
    CONSTRAINT ck_catalog_import_items_colors CHECK (colors_applied >= 0)
);
CREATE INDEX idx_catalog_import_items_run_outcome ON catalog_import_items (run_id, outcome);
CREATE INDEX idx_catalog_import_items_product ON catalog_import_items (product_id);

-- 호수의 색 칸 (S15P31A306-294). 호수 하나에 칸이 0..N개이고 듀오·팔레트도 칸마다 저장한다.
-- id 는 colorId(영구 식별자)라 칸을 지우고 다시 만들지 않는다. 칸 이름은 사이트 글자나 사진에 인쇄된 이름만이고,
-- 이름이 없으면 name 은 NULL 이고 name_source 는 NONE 이다 (순서대로 센 번호는 이름이 아니다).
-- 색 컬럼 4개는 모두 NULL('색을 못 구함')이거나 모두 값이 있어야 한다. BELOW_THRESHOLD·REJECTED 는 HEX 를 남긴 채 서비스에 쓰지 않는다.
-- 칸 순서 유니크는 한 트랜잭션에서 순서를 바꿀 수 있게 DEFERRABLE 이다.
-- 앱에서만 지키는 규칙: 사진·LLM·사이트 색값 출처는 color_estimated=true 이다 (ProductShadeColor).
-- 근거(이미지·영역·방법)는 DB 에 두지 않고 수집 실행 결과 파일에 둔다. 그 근거를 찾아가는 키만 둔다(S15P31A306-295):
-- source_item_id 는 이 칸의 현재 값을 만든 적재 건이고, source_evidence_key 는 그 건의 근거 키(<상품 번호>/<옵션 값>/<칸 순서>)다.
-- 둘은 함께 있거나 함께 없다(직접 넣은 칸은 둘 다 NULL).
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
    source_item_id      uuid,
    source_evidence_key varchar(400),
    created_at          timestamp(6) with time zone NOT NULL,
    updated_at          timestamp(6) with time zone NOT NULL,
    CONSTRAINT product_shade_colors_pkey PRIMARY KEY (id),
    CONSTRAINT fk_product_shade_colors_shade FOREIGN KEY (shade_id) REFERENCES product_shades (id),
    CONSTRAINT fk_product_shade_colors_source_item FOREIGN KEY (source_item_id) REFERENCES catalog_import_items (id),
    CONSTRAINT uk_product_shade_colors_shade_order UNIQUE (shade_id, sort_order) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT ck_product_shade_colors_name_pair CHECK ((name IS NULL) = (name_normalized IS NULL)),
    CONSTRAINT ck_product_shade_colors_name_source CHECK (
        (name IS NULL AND name_source = 'NONE')
        OR (name IS NOT NULL AND name_source IN ('SITE_TEXT', 'IMAGE_PRINT'))),
    CONSTRAINT ck_product_shade_colors_all_or_none CHECK (
        (color_hex IS NULL AND color_source IS NULL AND color_estimated IS NULL AND review_status IS NULL)
        OR (color_hex IS NOT NULL AND color_source IS NOT NULL AND color_estimated IS NOT NULL
            AND review_status IS NOT NULL)),
    CONSTRAINT ck_product_shade_colors_source_pair CHECK ((source_item_id IS NULL) = (source_evidence_key IS NULL)),
    CONSTRAINT ck_product_shade_colors_hex CHECK (color_hex ~ '^#[0-9A-F]{6}$'),
    CONSTRAINT ck_product_shade_colors_source CHECK (
        color_source IN ('SOURCE_VALUE', 'SWATCH_CHIP', 'PRODUCT_PHOTO', 'WEB_PHOTO', 'LLM_ESTIMATE', 'SAMPLE')),
    CONSTRAINT ck_product_shade_colors_review CHECK (
        review_status IN ('AUTO_APPROVED', 'BELOW_THRESHOLD', 'APPROVED', 'REJECTED'))
);
CREATE INDEX idx_product_shade_colors_shade_order ON product_shade_colors (shade_id, sort_order);
CREATE INDEX idx_product_shade_colors_source_item ON product_shade_colors (source_item_id);
