package com.mairor.backend.matching.service;

import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.products.entity.ProductShadeColor;
import java.util.Locale;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

/** 가이드 단계 기준색을 확정된 카탈로그 슬롯 색 또는 명시적인 수치 색상에서만 가져온다. */
@Component
public final class ReferenceColorResolver {

  private static final Pattern HEX = Pattern.compile("^#[0-9A-Fa-f]{6}$");

  public ReferenceColor resolve(GuideStepProductLink link, JsonNode targetColor) {
    ProductShadeColor linkedColor = usableLinkedColor(link);
    if (linkedColor != null) {
      return new ReferenceColor(
          linkedColor.getColor().getHex(), "CATALOG", linkedColor.getColor().isEstimated());
    }

    String hex = targetColorHex(targetColor);
    return hex == null
        ? null
        : new ReferenceColor(hex.toUpperCase(Locale.ROOT), "VIDEO_ESTIMATE", true);
  }

  private static ProductShadeColor usableLinkedColor(GuideStepProductLink link) {
    if (link == null
        || link.getReasonCode() == ReferenceMatchReason.LINK_CONFLICT
        || link.getMatchLevel() != ReferenceMatchLevel.SLOT) {
      return null;
    }
    ProductShadeColor color = link.getColor();
    return color != null && color.hasUsableColor() ? color : null;
  }

  private static String targetColorHex(JsonNode targetColor) {
    if (targetColor == null || !targetColor.isObject()) {
      return null;
    }
    JsonNode hex = targetColor.get("hex");
    if (hex == null || !hex.isTextual() || !HEX.matcher(hex.textValue()).matches()) {
      return null;
    }
    return hex.textValue();
  }

  public record ReferenceColor(String hex, String source, boolean estimated) {}
}
