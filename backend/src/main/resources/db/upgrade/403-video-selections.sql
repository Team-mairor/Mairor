-- S15P31A306-403: 회원 영상 선택 기록 표(API-VIDEO-001 · 인기 Top 4 API-VIDEO-005).
-- 표 · 인덱스를 더하기만 해서 옛 버전 앱과 함께 돌아도 깨지지 않는다. 새 버전 배포(ddl-auto=validate) 전에 적용한다.
-- 내용은 db/schema/analysis.sql 의 video_selections 와 같다.

BEGIN;

CREATE TABLE video_selections (
    id          uuid                        NOT NULL,
    video_id    uuid                        NOT NULL,
    user_id     uuid                        NOT NULL,
    selected_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT video_selections_pkey PRIMARY KEY (id),
    CONSTRAINT fk_video_selections_video FOREIGN KEY (video_id) REFERENCES videos (id) ON DELETE CASCADE,
    CONSTRAINT fk_video_selections_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX idx_video_selections_selected ON video_selections (selected_at);
CREATE INDEX idx_video_selections_user ON video_selections (user_id);

COMMIT;
