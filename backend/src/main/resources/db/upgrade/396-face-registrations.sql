-- S15P31A306-396 운영 추가분. photos/face_registrations가 없고 users/videos/guides가 있는 DB에 한 번 적용.
-- 새 테이블만 생성하므로 기존 사용자/가이드/파우치 행의 변환은 없다.
BEGIN;
-- S15P31A306-396: 비공개 사진 메타데이터와 실행별 기준 얼굴 등록.
-- users.sql → products.sql → analysis.sql 이후 적용한다. 이미지 바이트는 ObjectStorage에 저장한다.
-- Spring Session 만료 후에도 삭제 재시도가 가능해야 하므로 session_id에는 세션 FK를 걸지 않는다.
-- 원래 세션 ID는 내부 인가용 비밀 값이며 API/로그에 노출하지 않는다.
-- SQL 전용 규칙: 사진 소유자/세션 복합 FK, 등록 상태/파일 검증 CHECK, 미연결 등록 부분 유일 인덱스.
CREATE TABLE photos (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    session_id varchar(128) NOT NULL,
    kind varchar(24) NOT NULL,
    step_id varchar(200),
    storage_key varchar(500) NOT NULL,
    content_type varchar(32) NOT NULL,
    byte_size bigint NOT NULL,
    width integer NOT NULL,
    height integer NOT NULL,
    state varchar(24) NOT NULL,
    expires_at timestamp(6) with time zone,
    cleanup_requested_at timestamp(6) with time zone,
    next_cleanup_at timestamp(6) with time zone,
    cleanup_attempts integer NOT NULL DEFAULT 0,
    deleted_at timestamp(6) with time zone,
    created_at timestamp(6) with time zone NOT NULL,
    updated_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT photos_pkey PRIMARY KEY (id),
    CONSTRAINT fk_photos_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT uk_photos_storage_key UNIQUE (storage_key),
    CONSTRAINT uk_photos_owner_session UNIQUE (id, user_id, session_id),
    CONSTRAINT ck_photos_kind CHECK (
        (kind = 'FACE_REGISTRATION' AND step_id IS NULL)
        OR (kind = 'STEP' AND step_id IS NOT NULL AND btrim(step_id) <> '')),
    CONSTRAINT ck_photos_file CHECK (
        content_type IN ('image/jpeg', 'image/png')
        AND byte_size BETWEEN 1 AND 5242880 AND width > 0 AND height > 0),
    CONSTRAINT ck_photos_text CHECK (btrim(session_id) <> '' AND btrim(storage_key) <> ''),
    CONSTRAINT ck_photos_cleanup CHECK (
        cleanup_attempts >= 0 AND (
            (state IN ('PENDING_UPLOAD', 'AVAILABLE') AND cleanup_requested_at IS NULL
                AND next_cleanup_at IS NULL AND deleted_at IS NULL AND cleanup_attempts = 0)
            OR (state = 'CLEANUP_PENDING' AND cleanup_requested_at IS NOT NULL
                AND next_cleanup_at IS NOT NULL AND deleted_at IS NULL)
            OR (state = 'DELETED' AND cleanup_requested_at IS NOT NULL
                AND next_cleanup_at IS NULL AND deleted_at IS NOT NULL)))
);
CREATE INDEX idx_photos_cleanup ON photos (state, next_cleanup_at);
CREATE INDEX idx_photos_expiry ON photos (state, expires_at);

CREATE TABLE face_registrations (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    session_id varchar(128) NOT NULL,
    video_id uuid NOT NULL,
    guide_id uuid,
    photo_id uuid NOT NULL,
    execution_id uuid,
    status varchar(16) NOT NULL,
    lighting boolean NOT NULL,
    distance boolean NOT NULL,
    frontal boolean NOT NULL,
    unobstructed boolean NOT NULL,
    makeup_detected boolean NOT NULL,
    notice_version varchar(50) NOT NULL,
    agreed_at timestamp(6) with time zone NOT NULL,
    discarded_at timestamp(6) with time zone,
    created_at timestamp(6) with time zone NOT NULL,
    updated_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT face_registrations_pkey PRIMARY KEY (id),
    CONSTRAINT fk_face_registrations_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_face_registrations_video FOREIGN KEY (video_id) REFERENCES videos(id),
    CONSTRAINT fk_face_registrations_guide FOREIGN KEY (guide_id) REFERENCES guides(id),
    CONSTRAINT fk_face_registrations_photo_owner FOREIGN KEY (photo_id, user_id, session_id)
        REFERENCES photos(id, user_id, session_id),
    CONSTRAINT uk_face_registrations_photo UNIQUE (photo_id),
    CONSTRAINT uk_face_registrations_execution UNIQUE (execution_id),
    CONSTRAINT ck_face_registrations_status CHECK (
        (status = 'REGISTERED' AND execution_id IS NULL)
        OR (status IN ('LINKED', 'RETAINED') AND execution_id IS NOT NULL)),
    CONSTRAINT ck_face_registrations_checks CHECK (lighting AND distance AND frontal AND unobstructed),
    CONSTRAINT ck_face_registrations_notice CHECK (btrim(notice_version) <> '')
);
-- 동일 회원·세션·영상의 미연결 유효 등록은 하나. 재촬영 트랜잭션은 옛 등록 폐기 후 새 행을 연결한다.
CREATE UNIQUE INDEX uk_face_registrations_registered
    ON face_registrations (user_id, session_id, video_id)
    WHERE status = 'REGISTERED' AND discarded_at IS NULL;
CREATE INDEX idx_face_registrations_session ON face_registrations (user_id, session_id, status);
-- guide/video 소속, 사진 kind/상태는 서비스에서 검증한다.
-- execution_id FK는 executions 테이블이 생기는 395 migration에서 추가한다.

COMMIT;
