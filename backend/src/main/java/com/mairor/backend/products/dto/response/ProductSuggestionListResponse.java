package com.mairor.backend.products.dto.response;

import java.util.List;

/** 제품 후보 목록. 이름이 입력과 가까운 순서다. */
public record ProductSuggestionListResponse(List<ProductSuggestionResponse> items) {}
