package com.mairor.backend.products.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import tools.jackson.databind.JsonNode;

/**
 * 건 묶음 보내기. {@code items}의 각 항목은 {@code CollectedProduct}(shared/catalog-import) 형식이다. 항목은 요청 단계에서
 * 검사하지 않고 건마다 읽어서 한 건이 틀려도 나머지는 계속 처리한다. 개수와 배열 여부만 요청 단위로 검사한다.
 */
public record CatalogImportBatchRequest(
    @Schema(
            description =
                "수집 상품 1~100건. 각 항목은 shared/catalog-import 의 CollectedProduct 형식이다. 건마다 따로 검사하므로 한 건이 틀려도 나머지는 처리한다",
            type = "array",
            implementation = Object.class)
        JsonNode items) {}
