package com.mairor.backend.products.dto.response;

import java.util.List;

/** 제품 검색 결과. 정확히 일치하는 제품만 담으므로 0~1건이다. */
public record ProductListResponse(List<ProductResponse> items) {}
