package com.mairor.backend.matching.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class RecommendationCandidateSelectorTest {

  private final RecommendationCandidateSelector selector = new RecommendationCandidateSelector();

  @Test
  void sortsByClosestUsableColorThenPouchIdAndKeepsOnlyThreeItems() {
    UUID firstId = UUID.fromString("00000000-0000-0000-0000-000000000001");
    UUID secondId = UUID.fromString("00000000-0000-0000-0000-000000000002");
    UUID thirdId = UUID.fromString("00000000-0000-0000-0000-000000000003");
    UUID fourthId = UUID.fromString("00000000-0000-0000-0000-000000000004");

    List<RecommendationCandidateSelector.RankedCandidate> result =
        selector.select(
            "lip",
            "#FF0000",
            List.of(
                candidate(fourthId, "LIPSTICK", "#A00000"),
                candidate(firstId, "LIP_TINT", "#FF0000"),
                candidate(thirdId, "LIP_GLOSS", "#E00000"),
                candidate(secondId, "LIQUID_LIP", "#F00000"),
                candidate(UUID.randomUUID(), "LIP_BALM", "#FE0000")));

    assertThat(result)
        .extracting(candidate -> candidate.candidate().pouchItemId())
        .containsExactly(firstId, secondId, thirdId);
    assertThat(result.get(0).distance()).isZero();
  }

  @Test
  void choosesClosestSlotOnceForPaletteCandidate() {
    UUID itemId = UUID.randomUUID();
    UUID closeColorId = UUID.randomUUID();
    var candidate =
        new RecommendationCandidateSelector.Candidate(
            itemId,
            UUID.randomUUID(),
            UUID.randomUUID(),
            "EYE",
            "EYESHADOW_PALETTE",
            List.of(
                new RecommendationCandidateSelector.ColorOption(UUID.randomUUID(), "#FFFFFF"),
                new RecommendationCandidateSelector.ColorOption(closeColorId, "#F00000")));

    var result = selector.select("eyeshadow", "#FF0000", List.of(candidate));

    assertThat(result).hasSize(1);
    assertThat(result.getFirst().matchedColorId()).isEqualTo(closeColorId);
    assertThat(result.getFirst().matchedColorHex()).isEqualTo("#F00000");
  }

  @Test
  void excludesColorsBeyondTheMaximumDistance() {
    UUID closeId = UUID.randomUUID();
    UUID farId = UUID.randomUUID();

    var result =
        selector.select(
            "lip",
            "#FF0000",
            List.of(
                candidate(closeId, "LIP_TINT", "#E00000"),
                candidate(farId, "LIPSTICK", "#0000FF")));

    assertThat(result)
        .extracting(ranked -> ranked.candidate().pouchItemId())
        .containsExactly(closeId);
    assertThat(result.getFirst().distance())
        .isLessThanOrEqualTo(RecommendationCandidateSelector.MAX_COLOR_DISTANCE);
  }

  @Test
  void resolvesEqualDistanceByPouchItemId() {
    UUID firstId = UUID.fromString("00000000-0000-0000-0000-000000000001");
    UUID secondId = UUID.fromString("00000000-0000-0000-0000-000000000002");

    var result =
        selector.select(
            "lip",
            "#FF0000",
            List.of(
                candidate(secondId, "LIPSTICK", "#F00000"),
                candidate(firstId, "LIP_TINT", "#F00000")));

    assertThat(result)
        .extracting(candidate -> candidate.candidate().pouchItemId())
        .containsExactly(firstId, secondId);
  }

  @Test
  void sameRequiresBothProductAndShadeIds() {
    UUID productId = UUID.randomUUID();
    UUID shadeId = UUID.randomUUID();

    assertThat(RecommendationCandidateSelector.isSame(productId, shadeId, productId, shadeId))
        .isTrue();
    assertThat(RecommendationCandidateSelector.isSame(productId, null, productId, shadeId))
        .isFalse();
    assertThat(RecommendationCandidateSelector.isSame(productId, shadeId, productId, null))
        .isFalse();
  }

  private static RecommendationCandidateSelector.Candidate candidate(
      UUID itemId, String type, String hex) {
    return new RecommendationCandidateSelector.Candidate(
        itemId,
        UUID.randomUUID(),
        UUID.randomUUID(),
        "LIP",
        type,
        List.of(new RecommendationCandidateSelector.ColorOption(null, hex)));
  }
}
