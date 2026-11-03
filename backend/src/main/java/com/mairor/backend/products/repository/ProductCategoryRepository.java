package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.ProductCategory;
import java.util.List;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductCategoryRepository extends JpaRepository<ProductCategory, String> {

  /**
   * 카테고리 전체를 표시 순서({@code sortOrder}, {@code code})로 읽는다. 호환 부위도 함께 읽으며, 호환 부위가 없는 카테고리도 빈 목록으로
   * 포함된다.
   */
  @EntityGraph(attributePaths = "compatibleParts")
  List<ProductCategory> findAllByOrderBySortOrderAscCodeAsc();
}
