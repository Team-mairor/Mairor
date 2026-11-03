package com.mairor.backend.products.dto.request;

import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.support.CatalogText;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

/**
 * 제품 검색 쿼리 {@code ?category=&type=&brand=&name=}. 컨트롤러에서 {@code @Valid @ModelAttribute}로 받는다.
 *
 * <p>{@code @CatalogText} 는 springdoc 이 필수·길이 제한으로 알아보지 못해 brand·name 에 {@code requiredMode}·{@code
 * maxLength} 를 따로 적는다. 값은 엔티티 상수를 써서 검증 규칙과 함께 움직인다.
 *
 * <p>여기서는 형식만 본다. 카테고리·종류 코드가 있는지, 종류가 그 카테고리 소속인지는 서비스가 확인한다. 값은 받은 그대로 두고(바꾸거나 예외를 던지지 않는다) 비교용
 * 정규화는 서비스가 한다.
 */
public record ProductSearchQuery(
    @Schema(description = "카테고리 코드 (카테고리·종류 목록 API 의 code)", example = "LIP")
        @NotBlank(message = "필수 값입니다.")
        String category,
    @Schema(description = "종류 코드. category 소속이어야 한다", example = "LIP_TINT")
        @NotBlank(message = "필수 값입니다.")
        String type,
    @Schema(
            description = "브랜드. 길이는 앞뒤 공백(NBSP 등 유니코드 공백 포함)을 지운 뒤 센다. 대소문자·공백 차이는 같은 이름으로 본다",
            example = "롬앤",
            minLength = 1,
            maxLength = Product.BRAND_MAX_LENGTH,
            requiredMode = Schema.RequiredMode.REQUIRED)
        @CatalogText(max = Product.BRAND_MAX_LENGTH)
        String brand,
    @Schema(
            description = "제품명. 길이는 앞뒤 공백(NBSP 등 유니코드 공백 포함)을 지운 뒤 센다. 대소문자·공백 차이는 같은 이름으로 본다",
            example = "쥬시 래스팅 틴트",
            minLength = 1,
            maxLength = Product.NAME_MAX_LENGTH,
            requiredMode = Schema.RequiredMode.REQUIRED)
        @CatalogText(max = Product.NAME_MAX_LENGTH)
        String name) {}
