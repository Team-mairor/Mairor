package com.mairor.backend.products.service;

import com.mairor.backend.products.dto.response.ProductCategoryResponse;
import com.mairor.backend.products.dto.response.ProductTypeResponse;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.repository.ProductCategoryRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 화장품 카테고리·종류 목록 (API-POUCH-008).
 *
 * <p>카테고리(호환 부위 포함)와 전체 종류를 한 번씩, 쿼리 2번으로 읽고 메모리에서 카테고리별로 묶는다. 카테고리는 {@code sortOrder}, {@code
 * code} 순, 종류는 카테고리 안에서 {@code sortOrder}, {@code code} 순이다. 종류가 없는 카테고리도 빈 목록으로 포함한다.
 */
@Service
@Transactional(readOnly = true)
public class ProductCategoryService {

  private final ProductCategoryRepository categoryRepository;
  private final ProductTypeRepository typeRepository;

  public ProductCategoryService(
      ProductCategoryRepository categoryRepository, ProductTypeRepository typeRepository) {
    this.categoryRepository = categoryRepository;
    this.typeRepository = typeRepository;
  }

  public List<ProductCategoryResponse> list() {
    Map<String, List<ProductTypeResponse>> typesByCategory = new LinkedHashMap<>();
    for (ProductType type : typeRepository.findAllInDisplayOrder()) {
      typesByCategory
          .computeIfAbsent(type.getCategory().getCode(), code -> new ArrayList<>())
          .add(ProductTypeResponse.from(type));
    }

    // 호환 부위를 함께 읽는 컬렉션 fetch 라 행이 늘 수 있으므로 카테고리는 code 로 한 번만 담는다
    Map<String, ProductCategoryResponse> categories = new LinkedHashMap<>();
    for (ProductCategory category : categoryRepository.findAllByOrderBySortOrderAscCodeAsc()) {
      categories.putIfAbsent(
          category.getCode(),
          new ProductCategoryResponse(
              category.getCode(),
              category.getLabel(),
              category.isMatchable(),
              category.isShadeSelectable(),
              List.copyOf(typesByCategory.getOrDefault(category.getCode(), List.of())),
              category.getCompatibleParts().stream().sorted().toList()));
    }
    return List.copyOf(categories.values());
  }
}
