package com.mairor.backend.pouch.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.Objects;
import java.util.stream.Stream;
import tools.jackson.databind.JsonNode;

/** PATCH 요청의 필드 생략, 명시적 null, 값 전달을 구분한다. */
public record PouchUpdateRequest(
    @Schema(
            description = "CATALOG 또는 MANUAL. 생략하면 현재 방식을 유지한다.",
            type = "string",
            allowableValues = {"CATALOG", "MANUAL"})
        JsonNode registrationMode,
    @Schema(description = "선택할 카탈로그 제품 UUID. 생략하면 현재 연결을 유지한다.", type = "string", format = "uuid")
        JsonNode productId,
    @Schema(description = "선택할 제품 호수 UUID. 생략하면 현재 연결을 유지한다.", type = "string", format = "uuid")
        JsonNode shadeId,
    @Schema(description = "개인 항목 카테고리 코드", type = "string") JsonNode category,
    @Schema(description = "개인 항목 종류 코드", type = "string") JsonNode type,
    @Schema(description = "개인 항목 브랜드명", type = "string") JsonNode brand,
    @Schema(description = "개인 항목 제품명", type = "string") JsonNode name,
    @Schema(description = "호수명. null로 초기화할 수 있다.", type = "string", nullable = true)
        JsonNode shadeName,
    @Schema(
            description = "#RRGGBB 형식의 색상. null로 초기화할 수 있다.",
            type = "string",
            pattern = "^#[0-9A-Fa-f]{6}$",
            nullable = true)
        JsonNode colorHex) {

  /** 수정 필드가 하나도 전달되지 않은 요청인지 확인한다. */
  public boolean isEmpty() {
    return Stream.of(
            registrationMode, productId, shadeId, category, type, brand, name, shadeName, colorHex)
        .allMatch(Objects::isNull);
  }

  /** JSON에 해당 필드가 생략되지 않고 포함되었는지 확인한다. */
  public boolean isSpecified(Field field) {
    return value(field) != null;
  }

  /** JSON에 필드가 있고 명시적으로 null인지 확인한다. */
  public boolean isExplicitNull(Field field) {
    JsonNode value = value(field);
    return value != null && value.isNull();
  }

  private JsonNode value(Field field) {
    return switch (field) {
      case REGISTRATION_MODE -> registrationMode;
      case PRODUCT_ID -> productId;
      case SHADE_ID -> shadeId;
      case CATEGORY -> category;
      case TYPE -> type;
      case BRAND -> brand;
      case NAME -> name;
      case SHADE_NAME -> shadeName;
      case COLOR_HEX -> colorHex;
    };
  }

  public enum Field {
    REGISTRATION_MODE,
    PRODUCT_ID,
    SHADE_ID,
    CATEGORY,
    TYPE,
    BRAND,
    NAME,
    SHADE_NAME,
    COLOR_HEX
  }
}
