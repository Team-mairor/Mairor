package com.mairor.backend.analysis.extraction;

import java.util.List;

/**
 * AI 서버에 넘기는 가이드 입력 v2. 칸 설명은 {@code ai/docs/GUIDE_INPUT.md}, 형식은 {@code
 * shared/guide-input/guide_input.v2.schema.json}. 시각은 모두 영상 시작부터의 초다.
 */
public record GuideInput(String videoId, double durationSeconds, List<Step> steps) {

  public record Step(
      String stepId,
      int order,
      double startSeconds,
      double endSeconds,
      String makeup,
      String partLabel,
      String summary,
      Product product,
      Facts facts) {}

  /** 영상에 나온 제품. 여러 색이 든 제품이면 {@code palette}에 이 단계에서 고른 색이 있고, 한 가지 색이면 null. */
  public record Product(String brand, String name, String shade, Palette palette) {}

  public record Palette(Fact color) {}

  /** {@code area}만 필수, 나머지는 null 또는 빈 목록. */
  public record Facts(
      Fact area,
      Fact tool,
      Fact amount,
      Fact strength,
      Fact finishCue,
      List<Fact> tips,
      List<Fact> cautions) {}

  /**
   * @param source {@code voice} · {@code onscreenText} · {@code scene} · {@code estimated}
   * @param at 근거가 나온 시각(초). 단계 구간 밖이어도 된다
   */
  public record Fact(String value, String source, Double at) {}
}
