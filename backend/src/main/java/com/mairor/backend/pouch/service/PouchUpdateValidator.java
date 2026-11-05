package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.pouch.dto.PouchUpdateFields;
import com.mairor.backend.pouch.dto.PouchUpdateFields.PatchValue;
import com.mairor.backend.pouch.dto.PouchUpdateRequest;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

/** PATCH 필드 형식과 명시적 null 정책을 검증하고 typed 값으로 변환한다. */
@Component
public class PouchUpdateValidator {

  private static final Pattern HEX = Pattern.compile("^#[0-9A-Fa-f]{6}$");

  public PouchUpdateFields validate(PouchUpdateRequest request) {
    if (request == null || request.isEmpty()) {
      throw new BusinessException(HttpStatus.BAD_REQUEST, "POUCH_INVALID_UPDATE", "수정할 필드가 없습니다.");
    }

    return new PouchUpdateFields(
        registrationMode(request.registrationMode()),
        uuid(request.productId(), "productId"),
        uuid(request.shadeId(), "shadeId"),
        text(request.category(), "category", 20, false, false),
        text(request.type(), "type", 40, false, false),
        text(request.brand(), "brand", PouchItem.BRAND_MAX_LENGTH, false, false),
        text(request.name(), "name", PouchItem.NAME_MAX_LENGTH, false, false),
        text(request.shadeName(), "shadeName", PouchItem.SHADE_NAME_MAX_LENGTH, true, true),
        colorHex(request.colorHex()));
  }

  private static PatchValue<RegistrationMode> registrationMode(JsonNode node) {
    if (node == null) return PatchValue.missing();
    String value = requiredString(node, "registrationMode");
    try {
      return PatchValue.supplied(RegistrationMode.valueOf(value));
    } catch (IllegalArgumentException exception) {
      invalid("registrationMode", "CATALOG 또는 MANUAL이어야 합니다.");
      throw new AssertionError("unreachable");
    }
  }

  private static PatchValue<UUID> uuid(JsonNode node, String field) {
    if (node == null) return PatchValue.missing();
    String value = requiredString(node, field);
    try {
      return PatchValue.supplied(UUID.fromString(value));
    } catch (IllegalArgumentException exception) {
      invalid(field, "UUID 형식이어야 합니다.");
      throw new AssertionError("unreachable");
    }
  }

  private static PatchValue<String> text(
      JsonNode node, String field, int maxLength, boolean nullable, boolean blankAsNull) {
    if (node == null) return PatchValue.missing();
    if (node.isNull()) {
      if (nullable) return PatchValue.supplied(null);
      invalid(field, "null로 초기화할 수 없습니다.");
    }

    String value = CatalogTextNormalizer.trimmed(requiredString(node, field));
    if (value.isEmpty()) {
      if (blankAsNull) return PatchValue.supplied(null);
      invalid(field, "빈 값은 허용되지 않습니다.");
    }
    if (value.length() > maxLength) invalid(field, maxLength + "자 이하여야 합니다.");
    return PatchValue.supplied(value);
  }

  private static PatchValue<String> colorHex(JsonNode node) {
    PatchValue<String> value = text(node, "colorHex", 7, true, false);
    if (value.specified() && value.value() != null && !HEX.matcher(value.value()).matches()) {
      invalid("colorHex", "#RRGGBB 형식이어야 합니다.");
    }
    return value;
  }

  private static String requiredString(JsonNode node, String field) {
    if (!node.isString()) invalid(field, "문자열이어야 합니다.");
    return node.stringValue();
  }

  private static void invalid(String field, String reason) {
    throw new BusinessException(
        ErrorCode.VALIDATION_FAILED.status(),
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError(field, reason)),
        null);
  }
}
