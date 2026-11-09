package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.ProductShade;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductShadeRepository extends JpaRepository<ProductShade, UUID> {

  /** 새 참조 저장과 카탈로그의 호수/색 칸 교체가 같은 호수 행에서 직렬화되도록 잠근다. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select shade from ProductShade shade where shade.id = :shadeId")
  Optional<ProductShade> findByIdForUpdate(@Param("shadeId") UUID shadeId);

  /**
   * 제품의 호수를 {@code sortOrder}, {@code nameNormalized} 순으로 읽는다. 제품 안에서 {@code nameNormalized}가 유니크라
   * 순서가 하나로 정해지고, {@code idx_product_shades_product_order} 인덱스와 컬럼 순서가 같다.
   */
  List<ProductShade> findByProductIdOrderBySortOrderAscNameNormalizedAsc(UUID productId);
}
