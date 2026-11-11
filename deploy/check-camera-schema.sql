-- 읽기 전용 배포 사전 검사. DDL 적용은 배포 담당자가 별도로 수행한다.
BEGIN READ ONLY;
DO $$
BEGIN
  IF to_regclass('public.photos') IS NULL
     OR to_regclass('public.face_registrations') IS NULL THEN
    RAISE EXCEPTION '396-face-registrations.sql 적용 필요: photos/face_registrations 없음';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_index
    WHERE indexrelid = to_regclass('public.uk_face_registrations_registered')
      AND indrelid = 'public.face_registrations'::regclass
      AND indisunique AND indisvalid AND indpred IS NOT NULL
  ) OR (SELECT count(*) FROM pg_constraint
        WHERE conrelid = 'public.face_registrations'::regclass
          AND convalidated AND conname IN (
            'fk_face_registrations_photo_owner', 'ck_face_registrations_status',
            'uk_face_registrations_execution')) <> 3 THEN
    RAISE EXCEPTION '396 얼굴 등록 인덱스/FK/CHECK 누락 또는 미검증: 적용 상태 확인 필요';
  END IF;
END $$;
ROLLBACK;
