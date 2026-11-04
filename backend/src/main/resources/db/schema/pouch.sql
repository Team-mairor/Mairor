-- 개인 파우치 저장 구조 (S15P31A306-211). users.sql → products.sql → pouch.sql 순서로 적용한다.
-- 기존 DB에는 users.pouch_version 추가 후 이 파일을 적용한다. 상세 절차: backend/README.md.
-- 카탈로그 ID는 연결 정보, 표시 문자열·비교키·색상은 등록 시점의 개인 복사본이다.
-- 제품/호수의 소속과 shade_selectable 조건은 서비스에서 검증한다. JPA 자동 생성에는 SQL 전용 FK/CHECK가 없다.
CREATE TABLE pouch_items (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    registration_mode varchar(10) NOT NULL,
    product_id uuid,
    shade_id uuid,
    category_code varchar(20) NOT NULL,
    type_code varchar(40) NOT NULL,
    brand varchar(100) NOT NULL,
    name varchar(200) NOT NULL,
    shade_name varchar(100),
    brand_normalized varchar(200) NOT NULL,
    name_normalized varchar(400) NOT NULL,
    shade_name_normalized varchar(200) NOT NULL DEFAULT '',
    color_hex varchar(7),
    color_source varchar(20),
    color_estimated boolean,
    created_at timestamp(6) with time zone NOT NULL,
    updated_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT pouch_items_pkey PRIMARY KEY (id),
    CONSTRAINT fk_pouch_items_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_pouch_items_product FOREIGN KEY (product_id) REFERENCES products (id),
    CONSTRAINT fk_pouch_items_shade FOREIGN KEY (shade_id) REFERENCES product_shades (id),
    CONSTRAINT fk_pouch_items_category_type FOREIGN KEY (category_code, type_code)
        REFERENCES product_types (category_code, code),
    CONSTRAINT uk_pouch_items_user_brand_name_shade
        UNIQUE (user_id, brand_normalized, name_normalized, shade_name_normalized),
    CONSTRAINT ck_pouch_items_mode CHECK (
        (registration_mode = 'MANUAL' AND product_id IS NULL AND shade_id IS NULL)
        OR (registration_mode = 'CATALOG' AND product_id IS NOT NULL)),
    CONSTRAINT ck_pouch_items_normalized_nonempty CHECK (
        brand_normalized <> '' AND name_normalized <> ''),
    CONSTRAINT ck_pouch_items_shade_key CHECK (
        (shade_name IS NULL AND shade_name_normalized = '')
        OR (shade_name IS NOT NULL AND shade_name <> '' AND shade_name_normalized <> '')),
    CONSTRAINT ck_pouch_items_color CHECK (
        (color_hex IS NULL AND color_source IS NULL AND color_estimated IS NULL)
        OR (color_hex IS NOT NULL AND color_source IS NOT NULL AND color_estimated IS NOT NULL
            AND ((registration_mode = 'CATALOG' AND color_source = 'CATALOG')
                OR (registration_mode = 'MANUAL' AND color_source = 'USER_INPUT' AND color_estimated)))),
    CONSTRAINT ck_pouch_items_color_hex CHECK (color_hex ~ '^#[0-9A-F]{6}$')
);
CREATE INDEX idx_pouch_items_user_created ON pouch_items (user_id, created_at DESC, id DESC);
