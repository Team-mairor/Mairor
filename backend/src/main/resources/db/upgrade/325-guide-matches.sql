-- S15P31A306-325: 매칭 생성 시점의 버전과 결과 스냅샷을 저장한다.
-- 새 테이블 추가뿐이며 기존 회원·가이드·파우치 데이터의 변환은 없다.

BEGIN;

CREATE TABLE guide_matches (
    id                   uuid                        NOT NULL,
    user_id              uuid                        NOT NULL,
    guide_id             uuid                        NOT NULL,
    guide_version        integer                     NOT NULL,
    pouch_version        bigint                      NOT NULL,
    reference_version    integer                     NOT NULL,
    compatibility_version integer                    NOT NULL,
    match_snapshot       jsonb                       NOT NULL,
    created_at           timestamp(6) with time zone NOT NULL,
    CONSTRAINT guide_matches_pkey PRIMARY KEY (id),
    CONSTRAINT fk_guide_matches_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_guide_matches_guide FOREIGN KEY (guide_id) REFERENCES guides (id),
    CONSTRAINT ck_guide_matches_guide_version CHECK (guide_version >= 1),
    CONSTRAINT ck_guide_matches_pouch_version CHECK (pouch_version >= 0),
    CONSTRAINT ck_guide_matches_reference_version CHECK (reference_version >= 0),
    CONSTRAINT ck_guide_matches_compatibility_version CHECK (compatibility_version >= 1)
);
CREATE INDEX idx_guide_matches_user_created ON guide_matches (user_id, created_at DESC, id DESC);

COMMIT;
