package com.mairor.backend.analysis.extraction;

/**
 * Gemini 가 준 시각 → 초. Gemini 에는 시각을 {@code "MM:SS"} 문자열로 받는다. 초 숫자로 달라고 하면 322(=3분 22초)처럼 분초를 붙인 숫자로
 * 답해서다({@code ai/docs/GUIDE_INPUT.md} "BE가 할 일").
 */
final class StepTime {

  private StepTime() {}

  /**
   * {@code "MM:SS"}·{@code "H:MM:SS"}·{@code "MM:SS.s"}를 초로 바꾼다. 분이 60 을 넘어도 된다({@code "62:05"}).
   *
   * @return 초. 형식이 틀렸거나 초·분 자리가 60 이상이면 null
   */
  static Double parse(String value) {
    if (value == null || value.isBlank()) {
      return null;
    }
    String[] parts = value.trim().split(":");
    if (parts.length < 2 || parts.length > 3) {
      return null;
    }
    double total = 0;
    for (int i = 0; i < parts.length; i++) {
      double part;
      try {
        part = Double.parseDouble(parts[i]);
      } catch (NumberFormatException e) {
        return null;
      }
      boolean first = i == 0;
      if (part < 0 || (!first && part >= 60)) {
        return null;
      }
      total = total * 60 + part;
    }
    return total;
  }
}
