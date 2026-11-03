-- 화장품 카테고리·종류 기준 데이터 (S15P31A306-209). 모든 환경에 적용한다.
--
-- 적용 순서: db/schema/products.sql 다음. 여러 번 적용해도 된다.
--   - 같은 code 가 있으면 이 파일의 값으로 갱신한다 (라벨·순서·설정·소속 카테고리).
--   - 이미 제품이 연결된 종류의 category_code 를 바꾸면 fk_products_category_type 에 걸려 실패한다. 의도한 동작이다.
--   - 이 파일에서 행을 지워도 DB 의 행은 지워지지 않는다. 코드 삭제는 따로 처리한다.
--
-- 카테고리·종류는 기능명세 POUCH-004, matchable·shade_selectable 은 API 명세 API-POUCH-008 기준이다.
-- TODO(확인 필요 2): 종류 코드명 확정. 기능명세에 향수 하위 종류가 없어 PERFUME 하나를 임시로 둔다.
--   NAIL 은 호수 선택 카테고리지만 NAIL_FILE 에는 호수가 없다 (카테고리 단위 설정을 따른다).
-- 호환 부위(product_category_parts)는 값이 정해지지 않아 넣지 않는다. TODO(확인 필요 2)

INSERT INTO product_categories (code, label, matchable, shade_selectable, sort_order) VALUES
    ('BASE',      '베이스',   true,  true,  1),
    ('EYE',       '아이',     true,  true,  2),
    ('BROW',      '브로우',   true,  true,  3),
    ('CHEEK',     '치크',     true,  true,  4),
    ('LIP',       '립',       true,  true,  5),
    ('SKINCARE',  '스킨케어', false, false, 6),
    ('NAIL',      '네일',     false, true,  7),
    ('FRAGRANCE', '향수',     false, false, 8),
    ('TOOL',      '도구',     false, false, 9)
ON CONFLICT (code) DO UPDATE SET
    label            = EXCLUDED.label,
    matchable        = EXCLUDED.matchable,
    shade_selectable = EXCLUDED.shade_selectable,
    sort_order       = EXCLUDED.sort_order;

INSERT INTO product_types (code, category_code, label, sort_order) VALUES
    -- 베이스
    ('CUSHION',           'BASE',      '쿠션',          1),
    ('FOUNDATION',        'BASE',      '파운데이션',    2),
    ('CONCEALER',         'BASE',      '컨실러',        3),
    ('SUNSCREEN',         'BASE',      '선크림',        4),
    ('POWDER',            'BASE',      '파우더',        5),
    ('BASE_STICK',        'BASE',      '스틱',          6),
    -- 아이
    ('EYESHADOW_PALETTE', 'EYE',       '섀도우 팔레트', 1),
    ('MASCARA',           'EYE',       '마스카라',      2),
    ('EYELINER',          'EYE',       '아이라이너',    3),
    ('FALSE_LASHES',      'EYE',       '인조 속눈썹',   4),
    -- 브로우
    ('BROW_PENCIL',       'BROW',      '브로우 펜슬',   1),
    -- 치크
    ('BLUSHER',           'CHEEK',     '블러셔',        1),
    ('HIGHLIGHTER',       'CHEEK',     '하이라이터',    2),
    ('COMPACT',           'CHEEK',     '컴팩트',        3),
    -- 립
    ('LIPSTICK',          'LIP',       '립스틱',        1),
    ('LIP_GLOSS',         'LIP',       '립글로스',      2),
    ('LIP_TINT',          'LIP',       '립틴트',        3),
    ('LIP_BALM',          'LIP',       '립밤/팟',       4),
    ('LIQUID_LIP',        'LIP',       '리퀴드 립',     5),
    -- 스킨케어
    ('TONER',             'SKINCARE',  '토너',          1),
    ('SERUM_AMPOULE',     'SKINCARE',  '세럼/앰플',     2),
    ('CREAM',             'SKINCARE',  '크림',          3),
    ('CLEANSING_FOAM',    'SKINCARE',  '클렌징 폼',     4),
    ('CLEANSING_OIL',     'SKINCARE',  '클렌징 오일',   5),
    ('HAND_EYE_CREAM',    'SKINCARE',  '핸드/아이크림', 6),
    ('MASK_PACK',         'SKINCARE',  '마스크팩',      7),
    ('MIST',              'SKINCARE',  '미스트',        8),
    -- 네일
    ('NAIL_POLISH',       'NAIL',      '네일 폴리시',   1),
    ('NAIL_FILE',         'NAIL',      '네일 파일',     2),
    -- 향수 (TODO(확인 필요 2): 기능명세에 하위 종류 없음)
    ('PERFUME',           'FRAGRANCE', '향수',          1),
    -- 도구
    ('BRUSH',             'TOOL',      '브러시',        1),
    ('PUFF',              'TOOL',      '퍼프',          2),
    ('SPONGE',            'TOOL',      '스펀지',        3),
    ('EYELASH_CURLER',    'TOOL',      '뷰러',          4),
    ('HAND_MIRROR',       'TOOL',      '손거울',        5),
    ('TWEEZERS',          'TOOL',      '족집게',        6),
    ('COTTON_PAD',        'TOOL',      '화장솜',        7),
    ('COTTON_SWAB',       'TOOL',      '면봉',          8)
ON CONFLICT (code) DO UPDATE SET
    category_code = EXCLUDED.category_code,
    label         = EXCLUDED.label,
    sort_order    = EXCLUDED.sort_order;
