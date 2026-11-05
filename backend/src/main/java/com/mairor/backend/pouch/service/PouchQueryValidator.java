package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.pouch.dto.PouchListQuery;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.repository.ProductCategoryRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** 파우치 목록 필터 코드를 확인한다. 카탈로그 데이터는 읽기만 한다. */
@Component
@Transactional(readOnly = true)
public class PouchQueryValidator {

  private static final String UNKNOWN_CATEGORY = "없는 카테고리입니다.";
  private static final String UNKNOWN_TYPE = "없는 종류이거나 이 카테고리의 종류가 아닙니다.";

  private final ProductCategoryRepository categories;
  private final ProductTypeRepository types;

  public PouchQueryValidator(ProductCategoryRepository categories, ProductTypeRepository types) {
    this.categories = categories;
    this.types = types;
  }

  public void validate(PouchListQuery query) {
    String category = query.category();
    String type = query.type();

    if (category != null && (category.isBlank() || !categories.existsById(category))) {
      throw invalid("category", UNKNOWN_CATEGORY);
    }
    if (type == null) {
      return;
    }
    if (type.isBlank()) {
      throw invalid("type", UNKNOWN_TYPE);
    }

    Optional<ProductType> productType = types.findById(type);
    if (productType.isEmpty()
        || (category != null && !productType.get().getCategory().getCode().equals(category))) {
      throw invalid("type", UNKNOWN_TYPE);
    }
  }

  private static BusinessException invalid(String field, String reason) {
    return new BusinessException(
        ErrorCode.VALIDATION_FAILED.status(),
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError(field, reason)),
        null);
  }
}
