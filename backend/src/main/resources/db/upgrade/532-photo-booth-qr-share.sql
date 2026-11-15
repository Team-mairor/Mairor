-- S15P31A306-532: 회원 없이 만드는 만료 네컷 사진 QR 공유를 위한 사진 종류 추가.
BEGIN;

ALTER TABLE photos DROP CONSTRAINT IF EXISTS ck_photos_kind;
ALTER TABLE photos DROP CONSTRAINT IF EXISTS photos_kind_check;
ALTER TABLE photos ADD CONSTRAINT ck_photos_kind CHECK (
    (kind = 'FACE_REGISTRATION' AND user_id IS NOT NULL AND session_id IS NOT NULL AND step_id IS NULL)
    OR (kind = 'STEP' AND user_id IS NOT NULL AND session_id IS NOT NULL AND step_id IS NOT NULL AND btrim(step_id) <> '')
    OR (kind = 'PHOTO_BOOTH' AND user_id IS NULL AND session_id IS NULL AND step_id IS NULL)
);
ALTER TABLE photos ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE photos ALTER COLUMN session_id DROP NOT NULL;
ALTER TABLE photos DROP CONSTRAINT IF EXISTS ck_photos_text;
ALTER TABLE photos DROP CONSTRAINT IF EXISTS photos_text_check;
ALTER TABLE photos ADD CONSTRAINT ck_photos_text CHECK (
    btrim(storage_key) <> '' AND (session_id IS NULL OR btrim(session_id) <> '')
);

COMMIT;
