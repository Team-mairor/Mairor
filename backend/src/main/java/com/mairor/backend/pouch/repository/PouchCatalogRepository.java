package com.mairor.backend.pouch.repository;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

/** 파우치 등록에 필요한 카탈로그 읽기 전용 조회. 카탈로그를 저장하거나 갱신하지 않는다. */
public interface PouchCatalogRepository
    extends Repository<com.mairor.backend.products.entity.Product, UUID> {

  /** 제품·분류·선택 호수·색상을 한 SQL 스냅샷으로 읽는다. shadeId 가 null 이어도 제품 행은 반환한다. */
  @Query(
      value =
          """
          select p.id, p.brand, p.name, c.code as category_code, t.code as type_code,
                 c.shade_selectable, s.id as shade_id, s.name as shade_name,
                 s.color_hex, s.color_estimated
            from products p
            join product_types t on t.code = p.type_code and t.category_code = p.category_code
            join product_categories c on c.code = p.category_code
            left join product_shades s on s.product_id = p.id and s.id = :shadeId
           where p.id = :productId
          """,
      nativeQuery = true)
  List<Object[]> findSelection(@Param("productId") UUID productId, @Param("shadeId") UUID shadeId);
}
