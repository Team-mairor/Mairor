-- 영상 분석 부족분 수집 요청 (S15P31A306-518). 517 이 적용된 DB 에 변경분만 적용한다.
-- 빈 DB 에는 이 파일이 아니라 db/schema/pouch.sql 전체를 적용한다(결과가 같다. 다만 catalog_collect_requests 에 더한
-- 컬럼 5개는 맨 끝에 붙어 컬럼 순서만 다르다).
--
-- catalog_collect_requests 에 NULL 허용 컬럼 5개(gap·대상 제품·호수·칸·칸 이름)와 제약을 더하고, 기다리는 가이드 단계 테이블을 만든다.
-- 기존 행은 모두 trigger USER·gap NULL 이라 새 제약을 통과한다. 옛 버전 앱과 함께 돌아도 깨지지 않는다.
-- 새 버전 배포(ddl-auto=validate) 전에 적용한다. 한 번만 적용한다(이미 있으면 실패하고 전체가 롤백된다).
--
-- 적용 전에 확인한다.
--   1) 517 이 적용됐는지: SELECT to_regclass('catalog_collect_requests');      -- NULL 이 아니어야 한다
--   2) 아직 없는지:       SELECT to_regclass('catalog_collect_request_guides');  -- NULL 이어야 한다
--   3) GUIDE 요청이 없는지: SELECT count(*) FROM catalog_collect_requests WHERE trigger = 'GUIDE';  -- 0
-- 적용 후에 확인한다.
--   SELECT count(*) FROM catalog_collect_request_guides;  -- 0

BEGIN;

ALTER TABLE catalog_collect_requests
    ADD COLUMN gap               varchar(20),
    ADD COLUMN target_product_id uuid,
    ADD COLUMN target_shade_id   uuid,
    ADD COLUMN target_color_id   uuid,
    ADD COLUMN target_slot_label varchar(100),
    ADD CONSTRAINT fk_catalog_collect_requests_target_product FOREIGN KEY (target_product_id)
        REFERENCES products (id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_catalog_collect_requests_target_shade FOREIGN KEY (target_shade_id)
        REFERENCES product_shades (id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_catalog_collect_requests_target_color FOREIGN KEY (target_color_id)
        REFERENCES product_shade_colors (id) ON DELETE SET NULL,
    ADD CONSTRAINT ck_catalog_collect_requests_gap CHECK (
        gap IS NULL OR gap IN ('PRODUCT_MISSING', 'SHADE_MISSING', 'COLOR_MISSING')),
    ADD CONSTRAINT ck_catalog_collect_requests_trigger_gap CHECK ((trigger = 'GUIDE') = (gap IS NOT NULL));

-- 영상 분석 부족분 수집 요청을 기다리는 가이드 단계(S15P31A306-518). 같은 요청에 여러 가이드·단계가 붙는다.
-- 요청이 끝나면 붙은 가이드를 다시 대조한다. 가이드가 지워지면 함께 지운다.
CREATE TABLE catalog_collect_request_guides (
    id          uuid                        NOT NULL,
    request_id  uuid                        NOT NULL,
    guide_id    uuid                        NOT NULL,
    step_id     varchar(200)                NOT NULL,
    created_at  timestamp(6) with time zone NOT NULL,
    CONSTRAINT catalog_collect_request_guides_pkey PRIMARY KEY (id),
    CONSTRAINT fk_catalog_collect_request_guides_request FOREIGN KEY (request_id)
        REFERENCES catalog_collect_requests (id) ON DELETE CASCADE,
    CONSTRAINT fk_catalog_collect_request_guides_guide FOREIGN KEY (guide_id)
        REFERENCES guides (id) ON DELETE CASCADE,
    CONSTRAINT uk_catalog_collect_request_guides_request_step UNIQUE (request_id, guide_id, step_id)
);
CREATE INDEX idx_catalog_collect_request_guides_guide_created ON catalog_collect_request_guides (guide_id, created_at);

COMMIT;
