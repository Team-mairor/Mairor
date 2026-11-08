package com.mairor.backend.matching.service;

import java.util.Map;
import java.util.Set;

/** 매칭 대상 메이크업 단계와 자동 대체 가능한 카탈로그 종류를 명시적으로 연결한다. */
public final class PouchCompatibilityPolicy {

  private static final Map<String, Set<String>> COMPATIBLE_TYPES =
      Map.of(
          "foundation", Set.of("CUSHION", "FOUNDATION"),
          "eyeshadow", Set.of("EYESHADOW_PALETTE"),
          "eyeliner", Set.of("EYELINER"),
          "mascara", Set.of("MASCARA"),
          "brow", Set.of("BROW_PENCIL"),
          "blush", Set.of("BLUSHER"),
          "highlight", Set.of("HIGHLIGHTER"),
          "lip", Set.of("LIPSTICK", "LIP_TINT", "LIQUID_LIP", "LIP_GLOSS"));

  private PouchCompatibilityPolicy() {}

  /** 알 수 없는 메이크업 단계와 종류는 자동 후보에 포함하지 않는다. */
  public static boolean supports(String makeup, String typeCode) {
    if (makeup == null || typeCode == null) {
      return false;
    }
    return COMPATIBLE_TYPES.getOrDefault(makeup, Set.of()).contains(typeCode);
  }

  /** 수동 선택 패널에서 사용할 수 있는 자동 매칭 카테고리 코드. */
  public static String categoryFor(String makeup) {
    return switch (makeup == null ? "" : makeup) {
      case "foundation" -> "BASE";
      case "eyeshadow", "eyeliner", "mascara" -> "EYE";
      case "brow" -> "BROW";
      case "blush", "highlight", "contour" -> "CHEEK";
      case "lip" -> "LIP";
      default -> null;
    };
  }
}
