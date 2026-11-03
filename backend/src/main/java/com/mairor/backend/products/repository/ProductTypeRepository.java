package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.ProductType;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface ProductTypeRepository extends JpaRepository<ProductType, String> {

  /** 한 카테고리의 종류를 표시 순서({@code sortOrder}, {@code code})로 읽는다. */
  List<ProductType> findByCategoryCodeOrderBySortOrderAscCodeAsc(String categoryCode);

  /** 전체 종류를 카테고리 표시 순서, 그 안에서 종류 표시 순서로 읽는다. 카테고리도 함께 읽는다. */
  @Query(
      "select t from ProductType t join fetch t.category c"
          + " order by c.sortOrder, c.code, t.sortOrder, t.code")
  List<ProductType> findAllInDisplayOrder();
}
