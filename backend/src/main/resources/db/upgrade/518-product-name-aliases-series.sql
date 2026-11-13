-- 제품 이름 별칭의 유일 키에 상품을 넣는다 (S15P31A306-518). 517-product-name-aliases.sql 이 적용된 DB 에 적용한다.
-- 빈 DB 에는 이 파일이 아니라 db/schema/products.sql 전체를 적용한다(결과가 같다).
--
-- 한 제품이 시리즈별 상품으로 나뉘어 있으면(롬앤 블러 퍼지 틴트 #오리지널·#블랙스펙트럼) 같은 이름에 상품 여럿을 연결해야 한다.
-- 유일 키를 넓히기만 해서 기존 행은 모두 통과하고 옛 버전 앱과 함께 돌아도 깨지지 않는다(옛 코드는 같은 키를 한 번만 넣는다).
-- 새 버전 배포(ddl-auto=validate) 전에 적용한다. 한 번만 적용한다(이미 바뀌었으면 DROP 이 실패하고 전체가 롤백된다).
--
-- 적용 전에 확인한다: SELECT conname FROM pg_constraint WHERE conname = 'uk_product_name_aliases_key';  -- 한 줄
-- 적용 후에 확인한다: SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'uk_product_name_aliases_key';
--   -- UNIQUE (type_code, brand_normalized, name_compact, product_id)

BEGIN;
ALTER TABLE product_name_aliases DROP CONSTRAINT uk_product_name_aliases_key;
ALTER TABLE product_name_aliases ADD CONSTRAINT uk_product_name_aliases_key
    UNIQUE (type_code, brand_normalized, name_compact, product_id);
COMMIT;
