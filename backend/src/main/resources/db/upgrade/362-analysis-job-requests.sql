-- S15P31A306-362: 회원 분석 요청 기록 표(API-VIDEO-002). 합류한 회원의 조회 권한과 회원별 일일 신규 분석 한도에 쓴다.
-- 표 · 인덱스를 더하기만 해서 옛 버전 앱과 함께 돌아도 깨지지 않는다. 새 버전 배포(ddl-auto=validate) 전에 적용한다.
-- 내용은 db/schema/analysis.sql 의 analysis_job_requests 와 같다.

BEGIN;

CREATE TABLE analysis_job_requests (
    id              uuid                        NOT NULL,
    analysis_job_id uuid                        NOT NULL,
    user_id         uuid                        NOT NULL,
    receipt_type    varchar(20)                 NOT NULL,
    created_at      timestamp(6) with time zone NOT NULL,
    CONSTRAINT analysis_job_requests_pkey PRIMARY KEY (id),
    CONSTRAINT fk_analysis_job_requests_job FOREIGN KEY (analysis_job_id) REFERENCES analysis_jobs (id) ON DELETE CASCADE,
    CONSTRAINT fk_analysis_job_requests_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT uk_analysis_job_requests_job_user UNIQUE (analysis_job_id, user_id),
    CONSTRAINT ck_analysis_job_requests_receipt_type CHECK (receipt_type IN ('NEW_JOB', 'JOINED_JOB'))
);
CREATE INDEX idx_analysis_job_requests_user_created ON analysis_job_requests (user_id, created_at);

COMMIT;
