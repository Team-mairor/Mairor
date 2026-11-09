-- S15P31A306-357: 영상 전처리 노트북 임대 칸 3개(analysis_jobs). 칸 추가뿐이라 옛 버전 앱과 함께 돌아도 깨지지 않는다.
-- 새 버전 배포(ddl-auto=validate) 전에 적용한다. 내용은 db/schema/analysis.sql 의 같은 칸과 같다.

BEGIN;

ALTER TABLE analysis_jobs
    ADD COLUMN processor_lease_until timestamp(6) with time zone,
    ADD COLUMN processor_claims integer NOT NULL DEFAULT 0,
    ADD COLUMN processor_request_key varchar(500),
    ADD CONSTRAINT ck_analysis_jobs_processor_claims CHECK (processor_claims >= 0);

COMMIT;
