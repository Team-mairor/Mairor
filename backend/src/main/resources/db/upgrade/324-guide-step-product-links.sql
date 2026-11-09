-- S15P31A306-324: 운영 DB에 가이드 원본 제품 대조 구조를 추가한다.
-- 배포 전 기존 DB에 한 번 적용한다. 기존 가이드의 reference_version은 0으로 시작한다.
-- 적용 순서: guides.reference_version → guide_step_product_links → 색 변경 버전 갱신 트리거.

BEGIN;

ALTER TABLE guides
    ADD COLUMN reference_version integer NOT NULL DEFAULT 0,
    ADD CONSTRAINT ck_guides_reference_version CHECK (reference_version >= 0);

CREATE TABLE guide_step_product_links (
    id              uuid         NOT NULL,
    guide_id        uuid         NOT NULL,
    step_id         varchar(200) NOT NULL,
    product_id      uuid,
    shade_id        uuid,
    color_id        uuid,
    match_level     varchar(20)  NOT NULL,
    reason_code     varchar(40),
    created_at      timestamp(6) with time zone NOT NULL,
    updated_at      timestamp(6) with time zone NOT NULL,
    CONSTRAINT guide_step_product_links_pkey PRIMARY KEY (id),
    CONSTRAINT fk_guide_step_product_links_guide FOREIGN KEY (guide_id) REFERENCES guides (id),
    CONSTRAINT fk_guide_step_product_links_product FOREIGN KEY (product_id) REFERENCES products (id),
    CONSTRAINT fk_guide_step_product_links_shade FOREIGN KEY (shade_id) REFERENCES product_shades (id),
    CONSTRAINT fk_guide_step_product_links_color FOREIGN KEY (color_id) REFERENCES product_shade_colors (id),
    CONSTRAINT uk_guide_step_product_links_guide_step UNIQUE (guide_id, step_id),
    CONSTRAINT ck_guide_step_product_links_match_level CHECK (
        (match_level = 'NONE' AND product_id IS NULL AND shade_id IS NULL AND color_id IS NULL)
        OR (match_level = 'PRODUCT' AND product_id IS NOT NULL AND shade_id IS NULL AND color_id IS NULL)
        OR (match_level = 'SHADE' AND product_id IS NOT NULL AND shade_id IS NOT NULL AND color_id IS NULL)
        OR (match_level = 'SLOT' AND product_id IS NOT NULL AND shade_id IS NOT NULL AND color_id IS NOT NULL)
    ),
    CONSTRAINT ck_guide_step_product_links_reason_code CHECK (
        reason_code IS NULL OR reason_code IN (
            'PRODUCT_NOT_PROVIDED', 'PRODUCT_DATA_INCOMPLETE', 'CATEGORY_UNSUPPORTED', 'PRODUCT_NOT_FOUND',
            'PRODUCT_AMBIGUOUS', 'SHADE_NOT_PROVIDED', 'SHADE_NOT_FOUND', 'SHADE_AMBIGUOUS',
            'NO_COLOR_SLOTS', 'SLOT_UNIDENTIFIED', 'LINK_CONFLICT'
        )
    )
);

CREATE INDEX idx_guide_step_product_links_product
    ON guide_step_product_links (product_id) WHERE product_id IS NOT NULL;
CREATE INDEX idx_guide_step_product_links_shade
    ON guide_step_product_links (shade_id) WHERE shade_id IS NOT NULL;
CREATE INDEX idx_guide_step_product_links_color
    ON guide_step_product_links (color_id) WHERE color_id IS NOT NULL;

CREATE FUNCTION increment_guide_reference_version_for_color_change_fn()
RETURNS trigger
LANGUAGE plpgsql
AS '
BEGIN
    UPDATE guides g
       SET reference_version = g.reference_version + 1
     WHERE EXISTS (
         SELECT 1
           FROM guide_step_product_links l
          WHERE l.guide_id = g.id
            AND l.color_id = NEW.id
     );
    RETURN NEW;
END;
';

CREATE TRIGGER increment_guide_reference_version_for_color_change
    AFTER UPDATE OF color_hex, review_status ON product_shade_colors
    FOR EACH ROW
    WHEN (
        (CASE WHEN OLD.review_status IN ('AUTO_APPROVED', 'APPROVED') THEN OLD.color_hex END)
        IS DISTINCT FROM
        (CASE WHEN NEW.review_status IN ('AUTO_APPROVED', 'APPROVED') THEN NEW.color_hex END)
    )
    EXECUTE FUNCTION increment_guide_reference_version_for_color_change_fn();

COMMIT;
