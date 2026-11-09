-- 카탈로그 적재 실행 기록 (S15P31A306-295). 이미 products.sql 이 적용된 DB 에 변경분만 적용한다.
-- 빈 DB 에는 이 파일이 아니라 db/schema/products.sql 전체를 적용한다 (이 파일의 결과는 products.sql 과 같다.
-- 다만 기존 테이블에 더한 컬럼 2개는 맨 끝에 붙어서 컬럼 순서만 다르다).
--
-- 테이블 2개를 새로 만들고 product_shade_colors 에 NULL 허용 컬럼 2개와 제약·인덱스를 더한다.
-- 기존 행과 옛 버전 앱은 이 컬럼을 쓰지 않아서 함께 돌아도 깨지지 않는다.
-- 적용은 BE(정윤)가 머지 전에 한다 (deploy/README.md "DB 스키마"). 한 번만 적용한다 (이미 있으면 already exists 로 실패하고 전체가 롤백된다).
--
-- 적용 전에 확인한다.
--   1) 294 가 적용됐는지: SELECT to_regclass('product_shade_colors');  -- NULL 이 아니어야 한다
--   2) 이미 있는지 (둘 다 NULL 이어야 한다):
--      SELECT to_regclass('catalog_import_runs'), to_regclass('catalog_import_items');
-- 적용 후에 확인한다.
--   SELECT count(*) FROM catalog_import_runs;   -- 0
--   SELECT count(*) FROM catalog_import_items;  -- 0
--   SELECT count(*) FROM product_shade_colors WHERE source_item_id IS NOT NULL;  -- 0

BEGIN;

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

ALTER TABLE product_shade_colors
    ADD COLUMN source_item_id      uuid,
    ADD COLUMN source_evidence_key varchar(400),
    ADD CONSTRAINT fk_product_shade_colors_source_item FOREIGN KEY (source_item_id) REFERENCES catalog_import_items (id),
    ADD CONSTRAINT ck_product_shade_colors_source_pair CHECK ((source_item_id IS NULL) = (source_evidence_key IS NULL));
CREATE INDEX idx_product_shade_colors_source_item ON product_shade_colors (source_item_id);

COMMIT;
