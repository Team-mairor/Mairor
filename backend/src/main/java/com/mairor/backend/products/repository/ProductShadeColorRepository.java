package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.ProductShadeColor;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductShadeColorRepository extends JpaRepository<ProductShadeColor, UUID> {

  /**
   * 여러 호수의 색 칸을 한 번에 읽는다. 호수별 칸은 {@code sortOrder} 순이고, {@code (shade_id, sort_order)} 유니크라 순서가 하나로
   * 정해진다.
   */
  List<ProductShadeColor> findByShadeIdInOrderByShadeIdAscSortOrderAsc(Collection<UUID> shadeIds);
}
