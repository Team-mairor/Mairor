package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.pouch.dto.PouchRegistrationRequest;
import com.mairor.backend.pouch.dto.PouchUpdateFields;
import com.mairor.backend.pouch.dto.PouchUpdateFields.PatchValue;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchCatalogRepository;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.repository.ProductCategoryRepository;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/** 기존 항목과 PATCH 값을 합쳐 검증된 다음 상태를 만든다. 저장은 호출자가 처리한다. */
@Component
public class PouchUpdateCandidateBuilder {

  private final PouchRegistrationValidator registrationValidator;
  private final ProductCategoryRepository categories;
  private final PouchCatalogRepository catalog;

  public PouchUpdateCandidateBuilder(
      PouchRegistrationValidator registrationValidator,
      ProductCategoryRepository categories,
      PouchCatalogRepository catalog) {
    this.registrationValidator = registrationValidator;
    this.categories = categories;
    this.catalog = catalog;
  }

  public PouchItem build(UUID userId, PouchItem current, PouchUpdateFields fields) {
    if (current.getRegistrationMode() == RegistrationMode.CATALOG) {
      return updateCatalogItem(userId, current, fields);
    }
    return updateManualItem(userId, current, fields);
  }

  private PouchItem updateCatalogItem(UUID userId, PouchItem current, PouchUpdateFields fields) {
    boolean identifiersSpecified = specified(fields.productId()) || specified(fields.shadeId());
    boolean manualFieldsChanged =
        changed(fields.category(), current.getCategory())
            || changed(fields.brand(), current.getBrand())
            || changed(fields.name(), current.getName())
            || changed(fields.shadeName(), current.getShadeName())
            || changedColor(fields.colorHex(), current);
    RegistrationMode requestedMode = value(fields.registrationMode());

    if (requestedMode == RegistrationMode.MANUAL) {
      if (identifiersSpecified) invalidUpdate("MANUAL 전환 요청에 카탈로그 ID를 함께 보낼 수 없습니다.");
      requireManualTransitionFields(fields);
      return buildManual(userId, current, fields, true, true);
    }

    if (identifiersSpecified) {
      if (manualFieldsChanged) {
        invalidUpdate("카탈로그 선택과 직접 입력 필드를 함께 보낼 수 없습니다.");
      }
      return updateCatalogSelection(userId, current, fields);
    }

    if (requestedMode == RegistrationMode.CATALOG) {
      if (manualFieldsChanged) {
        invalidUpdate("CATALOG 유지 요청에는 직접 입력 필드를 보낼 수 없습니다.");
      }
      validateCatalogType(current.getProductId(), fields.type());
      return current;
    }

    if (manualFieldsChanged || changed(fields.type(), current.getType())) {
      return buildManual(
          userId,
          current,
          fields,
          false,
          current.getRegistrationMode() == RegistrationMode.CATALOG);
    }
    return current;
  }

  private PouchItem updateManualItem(UUID userId, PouchItem current, PouchUpdateFields fields) {
    RegistrationMode requestedMode = value(fields.registrationMode());
    boolean identifiersSpecified = specified(fields.productId()) || specified(fields.shadeId());
    boolean manualFieldsSpecified =
        specified(fields.category())
            || specified(fields.brand())
            || specified(fields.name())
            || specified(fields.shadeName())
            || specified(fields.colorHex());

    if (requestedMode == RegistrationMode.CATALOG) {
      if (manualFieldsSpecified) {
        invalidUpdate("CATALOG 전환 요청에는 직접 입력 필드를 보낼 수 없습니다.");
      }
      if (!specified(fields.productId()) || !specified(fields.type())) {
        invalidUpdate("CATALOG 전환에는 productId와 type이 필요합니다.");
      }
      return buildCatalogSelection(
          userId, fields.productId().value(), value(fields.shadeId()), fields.type().value(), true);
    }

    if (identifiersSpecified) {
      invalidUpdate("MANUAL 항목은 registrationMode를 CATALOG로 지정해야 카탈로그 ID를 연결할 수 있습니다.");
    }
    return buildManual(
        userId, current, fields, false, current.getRegistrationMode() == RegistrationMode.CATALOG);
  }

  private PouchItem buildManual(
      UUID userId,
      PouchItem current,
      PouchUpdateFields fields,
      boolean explicitTransition,
      boolean clearOmittedColor) {
    String category = merged(fields.category(), current.getCategory(), explicitTransition);
    String type = merged(fields.type(), current.getType(), explicitTransition);
    String brand = merged(fields.brand(), current.getBrand(), explicitTransition);
    String name = merged(fields.name(), current.getName(), explicitTransition);
    String shadeName = merged(fields.shadeName(), current.getShadeName(), explicitTransition);
    String colorHex =
        fields.colorHex().specified()
            ? fields.colorHex().value()
            : clearOmittedColor || current.getColor() == null ? null : current.getColor().getHex();

    ProductCategory finalCategory =
        categories
            .findById(category)
            .orElseThrow(() -> invalidProductException("category를 찾을 수 없습니다."));
    if (!finalCategory.isShadeSelectable()) {
      if (nonNullValue(fields.shadeName()) || nonNullValue(fields.colorHex())) {
        invalidUpdate("호수 선택이 없는 분류에는 shadeName과 colorHex를 지정할 수 없습니다.");
      }
      shadeName = null;
      colorHex = null;
    }

    return registrationValidator.prepare(
        userId,
        new PouchRegistrationRequest(
            RegistrationMode.MANUAL, null, null, category, type, brand, name, shadeName, colorHex));
  }

  private PouchItem updateCatalogSelection(
      UUID userId, PouchItem current, PouchUpdateFields fields) {
    UUID requestedProductId = value(fields.productId());
    UUID targetProductId = requestedProductId == null ? current.getProductId() : requestedProductId;
    boolean productChanged = !Objects.equals(targetProductId, current.getProductId());
    UUID targetShadeId =
        productChanged
            ? value(fields.shadeId())
            : specified(fields.shadeId()) ? value(fields.shadeId()) : current.getShadeId();
    boolean selectionChanged =
        productChanged || !Objects.equals(targetShadeId, current.getShadeId());

    if (!selectionChanged) {
      validateCatalogType(current.getProductId(), fields.type());
      return current;
    }

    return buildCatalogSelection(
        userId, targetProductId, targetShadeId, value(fields.type()), productChanged);
  }

  private PouchItem buildCatalogSelection(
      UUID userId,
      UUID productId,
      UUID shadeId,
      String expectedType,
      boolean requireShadeWhenSelectable) {
    List<Object[]> rows = catalog.findSelection(productId, shadeId);
    if (rows.isEmpty()) invalidProduct("제품을 찾을 수 없습니다.");
    Object[] row = rows.getFirst();
    String actualType = (String) row[4];
    if (expectedType != null && !expectedType.equals(actualType)) {
      invalidProduct("요청 type과 제품의 type이 다릅니다.");
    }
    boolean shadeSelectable = (Boolean) row[5];
    UUID resolvedShadeId = (UUID) row[6];
    if (shadeId != null && resolvedShadeId == null) {
      invalidProduct("호수가 제품에 속하지 않습니다.");
    }
    if (requireShadeWhenSelectable && shadeSelectable && resolvedShadeId == null) {
      invalidUpdate("호수 선택이 있는 제품으로 전환하려면 shadeId가 필요합니다.");
    }
    if (!shadeSelectable && shadeId != null) {
      invalidProduct("호수 선택이 없는 분류에는 호수를 연결할 수 없습니다.");
    }

    return registrationValidator.prepare(
        userId,
        new PouchRegistrationRequest(
            RegistrationMode.CATALOG,
            productId,
            resolvedShadeId,
            null,
            actualType,
            null,
            null,
            null,
            null));
  }

  private void validateCatalogType(UUID productId, PatchValue<String> requestedType) {
    if (!specified(requestedType)) return;
    List<Object[]> rows = catalog.findSelection(productId, null);
    if (rows.isEmpty()) invalidProduct("제품을 찾을 수 없습니다.");
    String actualType = (String) rows.getFirst()[4];
    if (!requestedType.value().equals(actualType)) {
      invalidProduct("요청 type과 제품의 type이 다릅니다.");
    }
  }

  private static void requireManualTransitionFields(PouchUpdateFields fields) {
    if (!specified(fields.category())
        || !specified(fields.type())
        || !specified(fields.brand())
        || !specified(fields.name())) {
      invalidUpdate("MANUAL 전환에는 category, type, brand, name이 필요합니다.");
    }
  }

  private static String merged(
      PatchValue<String> update, String currentValue, boolean explicitTransition) {
    return update.specified() ? update.value() : explicitTransition ? null : currentValue;
  }

  private static boolean specified(PatchValue<?> value) {
    return value.specified();
  }

  private static boolean changed(PatchValue<String> value, String currentValue) {
    return specified(value) && !Objects.equals(value.value(), currentValue);
  }

  private static boolean changedColor(PatchValue<String> value, PouchItem current) {
    if (!specified(value)) return false;
    String requestedHex = value.value();
    String currentHex = current.getColor() == null ? null : current.getColor().getHex();
    return !Objects.equals(
        requestedHex == null ? null : requestedHex.toUpperCase(java.util.Locale.ROOT), currentHex);
  }

  private static boolean nonNullValue(PatchValue<?> value) {
    return value.specified() && value.value() != null;
  }

  private static <T> T value(PatchValue<T> value) {
    return value.specified() ? value.value() : null;
  }

  private static void invalidUpdate(String message) {
    throw new BusinessException(HttpStatus.BAD_REQUEST, "POUCH_INVALID_UPDATE", message);
  }

  private static void invalidProduct(String message) {
    throw invalidProductException(message);
  }

  private static BusinessException invalidProductException(String message) {
    return new BusinessException(HttpStatus.BAD_REQUEST, "POUCH_INVALID_PRODUCT", message);
  }
}
