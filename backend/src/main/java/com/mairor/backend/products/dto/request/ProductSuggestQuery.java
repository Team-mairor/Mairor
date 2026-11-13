package com.mairor.backend.products.dto.request;

import com.mairor.backend.products.support.CatalogText;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

/**
 * 제품 후보 검색 쿼리 {@code ?q=&category=&type=&limit=}. 컨트롤러에서 {@code @Valid @ModelAttribute}로 받는다.
 *
 * <p>카테고리·종류는 좁히는 용도라 비워 둘 수 있다. 코드가 없는 값이면 후보가 없을 뿐 오류가 아니다.
 */
public record ProductSuggestQuery(
    @Schema(
            description =
                "찾을 말. 공백을 무시하고 브랜드+제품명에서 부분 일치를 본다. 공백으로 나눈 단어가 모두 들어 있어야 한다. 2자 미만이면 빈 목록이다",
            example = "퍼지",
            minLength = 1,
            maxLength = MAX_QUERY_LENGTH,
            requiredMode = Schema.RequiredMode.REQUIRED)
        @CatalogText(max = MAX_QUERY_LENGTH)
        String q,
    @Schema(description = "카테고리 코드. 주면 그 카테고리 제품만 찾는다", example = "LIP") String category,
    @Schema(description = "종류 코드. 주면 그 종류 제품만 찾는다", example = "LIP_TINT") String type,
    @Schema(description = "최대 개수. 기본 8, 최대 15", example = "8", defaultValue = "8")
        @Min(value = 1, message = "1 이상이어야 합니다.")
        @Max(value = MAX_LIMIT, message = "15 이하여야 합니다.")
        Integer limit) {

  public static final int MAX_QUERY_LENGTH = 50;
  public static final int DEFAULT_LIMIT = 8;
  public static final int MAX_LIMIT = 15;

  public int limitOrDefault() {
    return limit == null ? DEFAULT_LIMIT : limit;
  }
}
