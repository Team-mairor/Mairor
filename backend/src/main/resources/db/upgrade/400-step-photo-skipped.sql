-- S15P31A306-400: 제품 없이 넘긴(skipped) 단계에도 단계 사진을 연결한다(단계 사진 정책 E8 A안, S15P31A306-413).
-- 395 에서 만든 검사 제약 ck_execution_steps_skipped_photo 를 지운다. 제약을 빼기만 해서 옛 버전 앱과 함께 돌아도 깨지지 않는다
-- (옛 앱은 skipped 단계에 사진을 붙이지 않는다). 새 버전 배포 전에 적용한다. 다시 적용해도 된다(IF EXISTS).

BEGIN;

ALTER TABLE execution_steps DROP CONSTRAINT IF EXISTS ck_execution_steps_skipped_photo;

COMMIT;
