package com.mairor.backend.pouch.dto;

import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import java.time.Instant;
import java.util.UUID;

/** 개인 파우치 항목 응답. 표시값은 등록 시 저장한 복사본을 사용한다. */
public record PouchItemResponse(
    UUID pouchItemId,
    RegistrationMode registrationMode,
    UUID productId,
    UUID shadeId,
    String brand,
    String name,
    String category,
    String type,
    String shadeName,
    ColorInfo color,
    String colorSource,
    Instant createdAt,
    Instant updatedAt) {

  public record ColorInfo(String colorSpace, String hex, String source, boolean estimated) {}

  public static PouchItemResponse from(PouchItem item) {
    PouchColor color = item.getColor();
    ColorInfo colorInfo =
        color == null
            ? null
            : new ColorInfo("sRGB", color.getHex(), color.getSource().name(), color.isEstimated());
    return new PouchItemResponse(
        item.getId(),
        item.getRegistrationMode(),
        item.getProductId(),
        item.getShadeId(),
        item.getBrand(),
        item.getName(),
        item.getCategory(),
        item.getType(),
        item.getShadeName(),
        colorInfo,
        item.getColorSource(),
        item.getCreatedAt(),
        item.getUpdatedAt());
  }
}
