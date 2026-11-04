-- 영상 · 분석 작업 · 가이드 · LLM 호출 기록 (S15P31A306-307). 엔티티: videos/entity, analysis/entity, guides/entity
--
-- 운영 프로파일은 ddl-auto=validate 라서 이 테이블들이 먼저 있어야 앱이 기동한다.
-- 빈 DB 에만 적용한다. 이미 테이블이 있는 DB 에 다시 적용하면 already exists 로 실패한다.
-- 적용 순서: users.sql → products.sql → analysis.sql (analysis_jobs·guides 가 users 를 참조한다)
-- Flyway 를 도입하면 db/migration/V<번호>__create_analysis.sql 로 옮긴다. 번호는 Flyway 담당과 확인한다.
--
-- 제약·인덱스 이름은 엔티티 상수와 같아야 하고, AnalysisSchemaSqlTest·AnalysisConstraintSqlTest 가 확인한다.
--
-- JPA 가 표현하지 못해 이 파일에만 있는 규칙 (엔티티를 거치지 않은 데이터도 DB 가 막는다):
--   uk_analysis_jobs_video_active : 같은 영상의 진행 중(PENDING·RUNNING) 작업은 하나뿐이다 (API-VIDEO-002 "중복 생성하지 않는다")
--   uk_guides_video_approved      : 같은 영상의 공개(APPROVED) 가이드는 하나뿐이다
--
-- jsonb 칸의 모양은 레포 shared/ 스키마가 정한다. DB 는 JSON 인지만 본다.
--   guides.guide_input → shared/guide-input/guide_input.v1.schema.json
--   guides.explanation → shared/guide-job/guide_job_callback.v1.schema.json 의 guide
--   guides.area        → shared/guide-area/guide_area.v1.schema.json

-- 유튜브 영상. 메타는 YouTube Data API 값이며 30일 안에 갱신한다(ADR-002). 같은 youtube_video_id 는 행 하나다.
-- 영상 선택 화면은 임베드 재생을 하지 않으므로(11.03 결정) 재생 가능 여부 칸은 두지 않는다.
-- source_* 는 분석에 쓴 영상 파일의 값(ffprobe)이며, 파일을 확보하기 전에는 NULL 이다.
-- chapters: 설명란 챕터 [{"startSeconds": 0, "label": "시작"}, ...]
CREATE TABLE videos (
    id                      uuid                        NOT NULL,
    youtube_video_id        varchar(20)                 NOT NULL,
    title                   varchar(300)                NOT NULL,
    channel_title           varchar(200)                NOT NULL,
    duration_seconds        integer                     NOT NULL,
    thumbnail_url           varchar(1000),
    published_at            timestamp(6) with time zone,
    chapters                jsonb                       NOT NULL,
    source_object_key       varchar(500),
    source_width            integer,
    source_height           integer,
    source_fps              double precision,
    source_duration_seconds double precision,
    meta_refreshed_at       timestamp(6) with time zone NOT NULL,
    created_at              timestamp(6) with time zone NOT NULL,
    updated_at              timestamp(6) with time zone NOT NULL,
    CONSTRAINT videos_pkey PRIMARY KEY (id),
    CONSTRAINT uk_videos_youtube_video_id UNIQUE (youtube_video_id),
    CONSTRAINT ck_videos_duration CHECK (duration_seconds > 0)
);

-- 분석 작업. 상태·진행 단계 값은 API 명세 v2 AnalysisJobStatus 와 같다.
-- requested_by: 분석을 요청한 회원. 운영 명령으로 만든 작업은 NULL.
-- ai_job_id: AI 서버 POST /api/v1/guide-jobs 가 돌려준 jobId (콜백을 이 값으로 찾는다).
-- ai_requested_at: AI 에 가이드 생성을 맡긴 시각. 콜백 시간 초과의 기준이다(진행 숫자를 저장해도 바뀌지 않는다).
-- ai_progress: AI 진행 알림의 숫자 원본 {"explanation": {"done", "total"}, "frames": ..., "landmarks": ..., "area": ...}.
CREATE TABLE analysis_jobs (
    id               uuid                        NOT NULL,
    video_id         uuid                        NOT NULL,
    status           varchar(20)                 NOT NULL,
    progress_stage   varchar(30)                 NOT NULL,
    progress_percent integer,
    retryable        boolean                     NOT NULL,
    failure_code     varchar(50),
    failure_message  varchar(500),
    ai_job_id        varchar(64),
    ai_requested_at  timestamp(6) with time zone,
    ai_progress      jsonb,
    requested_by     uuid,
    attempt          integer                     NOT NULL,
    started_at       timestamp(6) with time zone,
    finished_at      timestamp(6) with time zone,
    created_at       timestamp(6) with time zone NOT NULL,
    updated_at       timestamp(6) with time zone NOT NULL,
    CONSTRAINT analysis_jobs_pkey PRIMARY KEY (id),
    CONSTRAINT fk_analysis_jobs_video FOREIGN KEY (video_id) REFERENCES videos (id),
    CONSTRAINT fk_analysis_jobs_requested_by FOREIGN KEY (requested_by) REFERENCES users (id),
    CONSTRAINT uk_analysis_jobs_ai_job_id UNIQUE (ai_job_id),
    CONSTRAINT ck_analysis_jobs_status CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    CONSTRAINT ck_analysis_jobs_progress_stage CHECK (progress_stage IN (
        'QUEUED', 'LOADING_VIDEO', 'SEGMENTING', 'RECOGNIZING_PRODUCTS',
        'EXTRACTING_STEPS', 'BUILDING_GUIDE', 'DONE')),
    CONSTRAINT ck_analysis_jobs_progress_percent CHECK (progress_percent BETWEEN 0 AND 100),
    CONSTRAINT ck_analysis_jobs_attempt CHECK (attempt >= 1)
);
CREATE UNIQUE INDEX uk_analysis_jobs_video_active ON analysis_jobs (video_id)
    WHERE status IN ('PENDING', 'RUNNING');
CREATE INDEX idx_analysis_jobs_status_created ON analysis_jobs (status, created_at);
CREATE INDEX idx_analysis_jobs_requested_by ON analysis_jobs (requested_by, created_at);

-- 가이드. 분석 작업 하나가 가이드 하나를 만든다. 검수 상태 값은 API 명세 v2 reviewStatus 와 같다.
-- explanation·area 는 AI 콜백이 오기 전에는 NULL 이다. 콜백은 설명·영역을 한 번에 보내므로, 콜백 뒤 area 가 NULL 이면 프레임 없이 맡긴 작업이다.
-- frames_manifest_key: 레퍼런스 프레임 목록(frames.json)의 S3 키.
CREATE TABLE guides (
    id                  uuid                        NOT NULL,
    video_id            uuid                        NOT NULL,
    analysis_job_id     uuid                        NOT NULL,
    version             integer                     NOT NULL,
    review_status       varchar(20)                 NOT NULL,
    mesh_version        varchar(10),
    guide_input         jsonb                       NOT NULL,
    explanation         jsonb,
    area                jsonb,
    frames_manifest_key varchar(500),
    reviewed_at         timestamp(6) with time zone,
    reviewed_by         uuid,
    created_at          timestamp(6) with time zone NOT NULL,
    updated_at          timestamp(6) with time zone NOT NULL,
    CONSTRAINT guides_pkey PRIMARY KEY (id),
    CONSTRAINT fk_guides_video FOREIGN KEY (video_id) REFERENCES videos (id),
    CONSTRAINT fk_guides_analysis_job FOREIGN KEY (analysis_job_id) REFERENCES analysis_jobs (id),
    CONSTRAINT fk_guides_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users (id),
    CONSTRAINT uk_guides_analysis_job UNIQUE (analysis_job_id),
    CONSTRAINT uk_guides_video_version UNIQUE (video_id, version),
    CONSTRAINT ck_guides_review_status CHECK (review_status IN ('NOT_READY', 'PENDING', 'APPROVED', 'REJECTED')),
    CONSTRAINT ck_guides_version CHECK (version >= 1)
);
CREATE UNIQUE INDEX uk_guides_video_approved ON guides (video_id) WHERE review_status = 'APPROVED';

-- LLM 호출 기록. 토큰·소요·비용 확인과 응답 원문 보존용. 분석 작업 밖에서 부른 호출은 analysis_job_id 가 NULL.
CREATE TABLE llm_calls (
    id              uuid                        NOT NULL,
    analysis_job_id uuid,
    provider        varchar(30)                 NOT NULL,
    model           varchar(80)                 NOT NULL,
    purpose         varchar(40)                 NOT NULL,
    status          varchar(20)                 NOT NULL,
    input_tokens    integer,
    output_tokens   integer,
    duration_ms     integer                     NOT NULL,
    error_code      varchar(50),
    response_body   text,
    created_at      timestamp(6) with time zone NOT NULL,
    CONSTRAINT llm_calls_pkey PRIMARY KEY (id),
    CONSTRAINT fk_llm_calls_analysis_job FOREIGN KEY (analysis_job_id) REFERENCES analysis_jobs (id),
    CONSTRAINT ck_llm_calls_status CHECK (status IN ('SUCCEEDED', 'FAILED')),
    CONSTRAINT ck_llm_calls_duration CHECK (duration_ms >= 0)
);
CREATE INDEX idx_llm_calls_analysis_job ON llm_calls (analysis_job_id, created_at);
