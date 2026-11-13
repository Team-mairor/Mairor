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
            AND ((registration_mode = 'CATALOG' AND color_source IN ('CATALOG', 'USER_INPUT'))
                OR (registration_mode = 'MANUAL' AND color_source = 'USER_INPUT' AND color_estimated)))),
    CONSTRAINT ck_pouch_items_color_hex CHECK (color_hex ~ '^#[0-9A-F]{6}$')
);
CREATE INDEX idx_pouch_items_user_created ON pouch_items (user_id, created_at DESC, id DESC);

-- 화장품 수집 요청 (S15P31A306-517). DB 에 없는 제품을 수집 큐(SQS)로 보내고 결과를 받는다.
-- id 가 수집 워커의 jobId 다. 같은 제품의 진행 중 요청은 하나뿐이고(request_key 부분 유니크), 요청한 회원·파우치 항목은
-- catalog_collect_request_users 에 붙인다. trigger GUIDE(영상 분석 부족분)는 S15P31A306-518 이 쓴다.
CREATE TABLE catalog_collect_requests (
    id               uuid                        NOT NULL,
    trigger          varchar(10)                 NOT NULL,
    request_key      varchar(800)                NOT NULL,
    category_code    varchar(20),
    type_code        varchar(40),
    brand            varchar(100)                NOT NULL,
    name             varchar(200),
    product_url      varchar(2000),
    shade_name       varchar(100),
    status           varchar(20)                 NOT NULL,
    reason           varchar(200),
    send_attempts    integer                     NOT NULL DEFAULT 0,
    sent_at          timestamp(6) with time zone,
    result_status    varchar(30),
    result_file      varchar(200),
    import_run_id    uuid,
    finished_at      timestamp(6) with time zone,
    created_at       timestamp(6) with time zone NOT NULL,
    updated_at       timestamp(6) with time zone NOT NULL,
    CONSTRAINT catalog_collect_requests_pkey PRIMARY KEY (id),
    CONSTRAINT fk_catalog_collect_requests_import_run FOREIGN KEY (import_run_id)
        REFERENCES catalog_import_runs (id),
    CONSTRAINT ck_catalog_collect_requests_trigger CHECK (trigger IN ('USER', 'GUIDE')),
    CONSTRAINT ck_catalog_collect_requests_status CHECK (
        status IN ('QUEUED', 'SENT', 'RESOLVED', 'UNRESOLVED', 'NOT_FOUND', 'FAILED')),
    CONSTRAINT ck_catalog_collect_requests_target CHECK ((name IS NULL) <> (product_url IS NULL)),
    CONSTRAINT ck_catalog_collect_requests_finished CHECK (
        (status IN ('QUEUED', 'SENT')) = (finished_at IS NULL)),
    CONSTRAINT ck_catalog_collect_requests_sent CHECK (status <> 'SENT' OR sent_at IS NOT NULL),
    CONSTRAINT ck_catalog_collect_requests_attempts CHECK (send_attempts >= 0)
);
CREATE UNIQUE INDEX uk_catalog_collect_requests_open_key ON catalog_collect_requests (request_key)
    WHERE status IN ('QUEUED', 'SENT');
CREATE INDEX idx_catalog_collect_requests_key_finished ON catalog_collect_requests (request_key, finished_at);
CREATE INDEX idx_catalog_collect_requests_status_updated ON catalog_collect_requests (status, updated_at);

-- 수집 요청을 낸 회원과 자동 연결 대상 파우치 항목. 같은 요청에 회원이 여럿 붙는다(합쳐진 요청).
-- pouch_item_updated_at 은 요청 때 항목의 수정 시각이다. 그 사이 회원이 항목을 바꿨으면 자동 연결하지 않는다.
CREATE TABLE catalog_collect_request_users (
    id                    uuid                        NOT NULL,
    request_id            uuid                        NOT NULL,
    user_id               uuid                        NOT NULL,
    pouch_item_id         uuid,
    pouch_item_updated_at timestamp(6) with time zone,
    link_result           varchar(30),
    created_at            timestamp(6) with time zone NOT NULL,
    CONSTRAINT catalog_collect_request_users_pkey PRIMARY KEY (id),
    CONSTRAINT fk_catalog_collect_request_users_request FOREIGN KEY (request_id)
        REFERENCES catalog_collect_requests (id) ON DELETE CASCADE,
    CONSTRAINT fk_catalog_collect_request_users_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_catalog_collect_request_users_pouch_item FOREIGN KEY (pouch_item_id)
        REFERENCES pouch_items (id) ON DELETE SET NULL,
    CONSTRAINT uk_catalog_collect_request_users_request_item UNIQUE (request_id, pouch_item_id)
);
CREATE INDEX idx_catalog_collect_request_users_user_created ON catalog_collect_request_users (user_id, created_at);
CREATE INDEX idx_catalog_collect_request_users_pouch_item ON catalog_collect_request_users (pouch_item_id);
