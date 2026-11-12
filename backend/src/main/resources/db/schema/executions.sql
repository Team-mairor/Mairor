-- S15P31A306-395: users → products → analysis → pouch → camera 이후 적용한다.
-- 완료 기록은 실행 완료와 원자적으로 생성한다. Report API 담당은 history_records 계약으로 조회/삭제 API를 구현한다.
-- 세션 삭제 뒤에도 종료 복구가 가능하도록 session_id에 Spring Session FK를 두지 않는다.
ALTER TABLE face_registrations ADD CONSTRAINT uk_face_registrations_owner_session
    UNIQUE (id, user_id, session_id);
ALTER TABLE photos ADD CONSTRAINT uk_photos_owner_session_step
    UNIQUE (id, user_id, session_id, step_id);
ALTER TABLE guide_matches ADD CONSTRAINT uk_guide_matches_owner_guide
    UNIQUE (id, user_id, guide_id);

CREATE TABLE guide_executions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    session_id varchar(128) NOT NULL,
    guide_id uuid NOT NULL,
    match_id uuid NOT NULL,
    face_registration_id uuid NOT NULL,
    guide_version integer NOT NULL,
    pouch_version bigint NOT NULL,
    reference_version integer NOT NULL,
    compatibility_version integer NOT NULL,
    guide_snapshot jsonb NOT NULL,
    status varchar(16) NOT NULL,
    photo_consent boolean,
    consent_policy_version varchar(50),
    consented_at timestamp(6) with time zone,
    record_id uuid,
    completed_at timestamp(6) with time zone,
    abandoned_at timestamp(6) with time zone,
    created_at timestamp(6) with time zone NOT NULL,
    updated_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT guide_executions_pkey PRIMARY KEY (id),
    CONSTRAINT fk_guide_executions_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_guide_executions_guide FOREIGN KEY (guide_id) REFERENCES guides(id),
    CONSTRAINT fk_guide_executions_match_owner_guide FOREIGN KEY (match_id, user_id, guide_id)
        REFERENCES guide_matches(id, user_id, guide_id),
    CONSTRAINT fk_guide_executions_face_owner FOREIGN KEY (face_registration_id, user_id, session_id)
        REFERENCES face_registrations(id, user_id, session_id),
    CONSTRAINT uk_guide_executions_face UNIQUE (face_registration_id),
    CONSTRAINT uk_guide_executions_record UNIQUE (record_id),
    CONSTRAINT uk_guide_executions_owner_session UNIQUE (id, user_id, session_id),
    CONSTRAINT ck_guide_executions_versions CHECK (
        guide_version >= 1 AND pouch_version >= 0
        AND reference_version >= 0 AND compatibility_version >= 1),
    CONSTRAINT ck_guide_executions_snapshot CHECK (jsonb_typeof(guide_snapshot) = 'object'),
    CONSTRAINT ck_guide_executions_session CHECK (btrim(session_id) <> ''),
    CONSTRAINT ck_guide_executions_consent CHECK (
        (photo_consent IS NULL AND consent_policy_version IS NULL AND consented_at IS NULL)
        OR (photo_consent IS NOT NULL AND consent_policy_version IS NOT NULL
            AND btrim(consent_policy_version) <> ''
            AND ((photo_consent AND consented_at IS NOT NULL)
                OR (NOT photo_consent AND consented_at IS NULL)))),
    CONSTRAINT ck_guide_executions_status CHECK (
        (status = 'IN_PROGRESS' AND record_id IS NULL AND completed_at IS NULL AND abandoned_at IS NULL)
        OR (status = 'COMPLETED' AND record_id IS NOT NULL AND completed_at IS NOT NULL AND abandoned_at IS NULL)
        OR (status = 'ABANDONED' AND record_id IS NULL AND completed_at IS NULL AND abandoned_at IS NOT NULL))
);
CREATE INDEX idx_guide_executions_session ON guide_executions (user_id, session_id, status);

CREATE TABLE execution_steps (
    id uuid NOT NULL,
    execution_id uuid NOT NULL,
    user_id uuid NOT NULL,
    session_id varchar(128) NOT NULL,
    step_id varchar(200) NOT NULL,
    position integer NOT NULL,
    skipped boolean NOT NULL,
    step_snapshot jsonb NOT NULL,
    photo_id uuid,
    CONSTRAINT execution_steps_pkey PRIMARY KEY (id),
    CONSTRAINT fk_execution_steps_execution_owner FOREIGN KEY (execution_id, user_id, session_id)
        REFERENCES guide_executions(id, user_id, session_id),
    CONSTRAINT fk_execution_steps_photo_owner_step FOREIGN KEY (photo_id, user_id, session_id, step_id)
        REFERENCES photos(id, user_id, session_id, step_id),
    CONSTRAINT uk_execution_steps_step UNIQUE (execution_id, step_id),
    CONSTRAINT uk_execution_steps_position UNIQUE (execution_id, position),
    CONSTRAINT uk_execution_steps_photo UNIQUE (photo_id),
    CONSTRAINT ck_execution_steps_step CHECK (btrim(step_id) <> '' AND position >= 0),
    CONSTRAINT ck_execution_steps_snapshot CHECK (jsonb_typeof(step_snapshot) = 'object')
);

-- 실행 행을 먼저 저장/flush한 뒤 얼굴 등록을 LINKED로 전환한다.
ALTER TABLE face_registrations ADD CONSTRAINT fk_face_registrations_execution_owner
    FOREIGN KEY (execution_id, user_id, session_id)
    REFERENCES guide_executions(id, user_id, session_id);

CREATE TABLE history_records (
    id uuid NOT NULL,
    execution_id uuid NOT NULL,
    user_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version integer NOT NULL,
    video_id uuid NOT NULL,
    youtube_video_id varchar(20) NOT NULL,
    video_title varchar(300) NOT NULL,
    channel_title varchar(200) NOT NULL,
    thumbnail_url varchar(1000),
    completed_at timestamp(6) with time zone NOT NULL,
    completed_photo_id uuid,
    step_count integer NOT NULL,
    substitute_count integer NOT NULL,
    record_snapshot jsonb NOT NULL,
    created_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT history_records_pkey PRIMARY KEY (id),
    CONSTRAINT fk_history_records_execution FOREIGN KEY (execution_id) REFERENCES guide_executions(id),
    CONSTRAINT fk_history_records_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_history_records_guide FOREIGN KEY (guide_id) REFERENCES guides(id),
    CONSTRAINT fk_history_records_video FOREIGN KEY (video_id) REFERENCES videos(id),
    CONSTRAINT fk_history_records_completed_photo FOREIGN KEY (completed_photo_id) REFERENCES photos(id),
    CONSTRAINT uk_history_records_execution UNIQUE (execution_id),
    CONSTRAINT ck_history_records_counts CHECK (
        guide_version >= 1 AND step_count >= 0 AND substitute_count BETWEEN 0 AND step_count),
    CONSTRAINT ck_history_records_snapshot CHECK (jsonb_typeof(record_snapshot) = 'object'),
    CONSTRAINT ck_history_records_text CHECK (
        btrim(youtube_video_id) <> '' AND btrim(video_title) <> '' AND btrim(channel_title) <> '')
);
CREATE INDEX idx_history_records_owner_completed
    ON history_records (user_id, completed_at DESC, id DESC);

-- match/guide 일치·최신성, 얼굴/실행의 상호 연결·상태, 같은 세션 시작 직렬화는 서비스 책임이다.
-- 사진 상태/동의 인가 및 교체/삭제 예약도 실행 잠금 안에서 수행한다.
