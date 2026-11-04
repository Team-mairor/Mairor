package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.pouch.dto.PouchRegistrationRequest;
import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchCatalogRepository;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.repository.ProductCategoryRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/** 등록 요청을 확인하고 저장할 개인 항목을 준비한다. 이 단계에서는 저장을 수행하지 않는다. */
@Component
public class PouchRegistrationValidator {

  private static final Pattern HEX = Pattern.compile("^#[0-9A-Fa-f]{6}$");

  private final ProductCategoryRepository categories;
  private final ProductTypeRepository types;
  private final PouchCatalogRepository catalog;

  public PouchRegistrationValidator(
      ProductCategoryRepository categories,
      ProductTypeRepository types,
      PouchCatalogRepository catalog) {
    this.categories = categories;
    this.types = types;
    this.catalog = catalog;
  }

  /** 인증 회원 ID와 요청을 받아 검증된 개인 항목을 만든다. DB 저장·버전 증가는 호출자가 처리한다. */
  public PouchItem prepare(UUID userId, PouchRegistrationRequest request) {
    if (userId == null || request == null || request.registrationMode() == null) {
      invalid("registrationMode", "필수 값입니다.");
    }
    return request.registrationMode() == RegistrationMode.CATALOG
        ? prepareCatalog(userId, request)
        : prepareManual(userId, request);
  }

  private PouchItem prepareCatalog(UUID userId, PouchRegistrationRequest request) {
    if (request.productId() == null) invalid("productId", "필수 값입니다.");
    if (request.type() == null || request.type().isBlank()) invalid("type", "필수 값입니다.");
    if (hasAny(
        request.category(),
        request.brand(),
        request.name(),
        request.shadeName(),
        request.colorHex())) {
      invalid("registrationMode", "CATALOG 등록에는 카탈로그 ID와 type만 보낼 수 있습니다.");
    }

    List<Object[]> rows = catalog.findSelection(request.productId(), request.shadeId());
    if (rows.isEmpty()) invalidProduct("제품을 찾을 수 없습니다.");
    Object[] row = rows.getFirst();
    String category = (String) row[3];
    String type = (String) row[4];
    if (!type.equals(request.type())) invalidProduct("요청 type과 제품의 type이 다릅니다.");

    boolean shadeSelectable = (Boolean) row[5];
    UUID shadeId = (UUID) row[6];
    String shadeName = (String) row[7];
    if (shadeSelectable && (request.shadeId() == null || shadeId == null)) {
      invalidProduct("호수를 선택해야 합니다.");
    }
    if (!shadeSelectable && request.shadeId() != null) {
      invalidProduct("호수 선택이 없는 분류에는 호수를 연결할 수 없습니다.");
    }

    String colorHex = (String) row[8];
    Boolean estimated = (Boolean) row[9];
    PouchColor color =
        colorHex == null ? null : PouchColor.catalog(colorHex, Boolean.TRUE.equals(estimated));
    return new PouchItem(
        userId,
        RegistrationMode.CATALOG,
        request.productId(),
        shadeId,
        category,
        type,
        (String) row[1],
        (String) row[2],
        shadeName,
        color);
  }

  private PouchItem prepareManual(UUID userId, PouchRegistrationRequest request) {
    if (request.productId() != null || request.shadeId() != null) {
      invalid("productId", "MANUAL 등록에는 카탈로그 ID를 보낼 수 없습니다.");
    }
    String categoryCode = requiredText(request.category(), "category", 20);
    String typeCode = requiredText(request.type(), "type", 40);
    String brand = requiredText(request.brand(), "brand", PouchItem.BRAND_MAX_LENGTH);
    String name = requiredText(request.name(), "name", PouchItem.NAME_MAX_LENGTH);
    String shadeName =
        optionalText(request.shadeName(), "shadeName", PouchItem.SHADE_NAME_MAX_LENGTH);
    String colorHex = optionalText(request.colorHex(), "colorHex", 7);
    if (colorHex != null && !HEX.matcher(colorHex).matches()) {
      invalid("colorHex", "#RRGGBB 형식이어야 합니다.");
    }

    ProductCategory category =
        categories
            .findById(categoryCode)
            .orElseThrow(() -> invalidProductException("category를 찾을 수 없습니다."));
    ProductType type =
        types.findById(typeCode).orElseThrow(() -> invalidProductException("type을 찾을 수 없습니다."));
    if (!categoryCode.equals(type.getCategory().getCode())) {
      invalidProduct("type이 category에 속하지 않습니다.");
    }
    if (!category.isShadeSelectable() && (shadeName != null || colorHex != null)) {
      invalidProduct("호수 선택이 없는 분류에는 shadeName과 colorHex를 입력할 수 없습니다.");
    }

    PouchColor color = colorHex == null ? null : PouchColor.userInput(colorHex);
    return new PouchItem(
        userId,
        RegistrationMode.MANUAL,
        null,
        null,
        categoryCode,
        typeCode,
        brand,
        name,
        shadeName,
        color);
  }

  private static String requiredText(String value, String field, int max) {
    if (value == null) invalid(field, "필수 값입니다.");
    String trimmed = CatalogTextNormalizer.trimmed(value);
    if (trimmed.isEmpty()) invalid(field, "필수 값입니다.");
    if (trimmed.length() > max) invalid(field, max + "자 이하여야 합니다.");
    return trimmed;
  }

  private static String optionalText(String value, String field, int max) {
    if (value == null) return null;
    String trimmed = CatalogTextNormalizer.trimmed(value);
    if (trimmed.isEmpty()) return null;
    if (trimmed.length() > max) invalid(field, max + "자 이하여야 합니다.");
    return trimmed;
  }

  private static boolean hasAny(String... values) {
    for (String value : values) if (value != null) return true;
    return false;
  }

  private static void invalid(String field, String reason) {
    throw new BusinessException(
        ErrorCode.VALIDATION_FAILED.status(),
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError(field, reason)),
        null);
  }

  private static void invalidProduct(String message) {
    throw invalidProductException(message);
  }

  private static BusinessException invalidProductException(String message) {
    return new BusinessException(HttpStatus.BAD_REQUEST, "POUCH_INVALID_PRODUCT", message);
  }
}
