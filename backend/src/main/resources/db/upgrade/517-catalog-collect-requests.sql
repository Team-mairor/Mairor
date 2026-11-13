-- 화장품 수집 요청 (S15P31A306-517). 이미 pouch.sql·295 가 적용된 DB 에 변경분만 적용한다.
-- 빈 DB 에는 이 파일이 아니라 db/schema/pouch.sql 전체를 적용한다(결과가 같다).
--
-- 새 테이블 2개와 인덱스를 더하고, pouch_items 의 색 검사 제약을 넓힌다(카탈로그에 자동 연결된 항목이 회원이 넣은 색을
-- USER_INPUT 으로 유지할 수 있게). 제약을 넓히기만 해서 기존 행은 모두 통과하고 옛 버전 앱과 함께 돌아도 깨지지 않는다.
-- 새 버전 배포(ddl-auto=validate) 전에 적용한다.
-- 한 번만 적용한다(이미 있으면 already exists 로 실패하고 전체가 롤백된다).
--
-- 적용 전에 확인한다.
--   1) 참조하는 테이블이 있는지 (모두 NULL 이 아니어야 한다):
--      SELECT to_regclass('pouch_items'), to_regclass('catalog_import_runs');
--   2) 이미 있는지 (둘 다 NULL 이어야 한다):
--      SELECT to_regclass('catalog_collect_requests'), to_regclass('catalog_collect_request_users');
-- 적용 후에 확인한다.
--   SELECT count(*) FROM catalog_collect_requests;       -- 0
--   SELECT count(*) FROM catalog_collect_request_users;  -- 0

BEGIN;
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

ALTER TABLE pouch_items DROP CONSTRAINT ck_pouch_items_color;
ALTER TABLE pouch_items ADD CONSTRAINT ck_pouch_items_color CHECK (
    (color_hex IS NULL AND color_source IS NULL AND color_estimated IS NULL)
    OR (color_hex IS NOT NULL AND color_source IS NOT NULL AND color_estimated IS NOT NULL
        AND ((registration_mode = 'CATALOG' AND color_source IN ('CATALOG', 'USER_INPUT'))
            OR (registration_mode = 'MANUAL' AND color_source = 'USER_INPUT' AND color_estimated))));

COMMIT;
