package com.mairor.backend.products.dto.response;

import java.util.List;

/** 화장품 카테고리 전체. 표시 순서대로 온다. */
public record ProductCategoryListResponse(List<ProductCategoryResponse> items) {}
