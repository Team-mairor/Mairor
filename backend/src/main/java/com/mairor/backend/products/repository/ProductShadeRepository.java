package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.ProductShade;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductShadeRepository extends JpaRepository<ProductShade, UUID> {

  /**
   * 제품의 호수를 {@code sortOrder}, {@code nameNormalized} 순으로 읽는다. 제품 안에서 {@code nameNormalized}가 유니크라
   * 순서가 하나로 정해지고, {@code idx_product_shades_product_order} 인덱스와 컬럼 순서가 같다.
   */
  List<ProductShade> findByProductIdOrderBySortOrderAscNameNormalizedAsc(UUID productId);
}
