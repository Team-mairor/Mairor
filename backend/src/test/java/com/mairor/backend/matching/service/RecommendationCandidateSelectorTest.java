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
  void keepsFarColorsAfterTheCloseOnesWithoutADistanceLimit() {
    UUID closeId = UUID.randomUUID();
    UUID farId = UUID.randomUUID();

    var result =
        selector.select(
            "lip",
            "#FF0000",
            List.of(
                candidate(farId, "LIPSTICK", "#0000FF"),
                candidate(closeId, "LIP_TINT", "#E00000")));

    assertThat(result)
        .extracting(ranked -> ranked.candidate().pouchItemId())
        .containsExactly(closeId, farId);
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

  @Test
  void selectAllKeepsEveryCompatibleColoredItemInOrderWhileSelectStaysAtThree() {
    UUID a = UUID.fromString("00000000-0000-0000-0000-000000000001");
    UUID b = UUID.fromString("00000000-0000-0000-0000-000000000002");
    UUID c = UUID.fromString("00000000-0000-0000-0000-000000000003");
    UUID d = UUID.fromString("00000000-0000-0000-0000-000000000004");
    UUID far = UUID.fromString("00000000-0000-0000-0000-000000000005");
    var candidates =
        List.of(
            candidate(d, "LIPSTICK", "#E00000"),
            candidate(a, "LIP_TINT", "#FF0000"),
            candidate(c, "LIP_GLOSS", "#F00000"),
            candidate(b, "LIQUID_LIP", "#FA0000"),
            candidate(far, "LIPSTICK", "#0000FF"),
            candidate(UUID.randomUUID(), "EYESHADOW_PALETTE", "#FF0000"));

    var all = selector.selectAll("lip", "#FF0000", candidates);

    assertThat(all)
        .extracting(ranked -> ranked.candidate().pouchItemId())
        .containsExactly(a, b, c, d, far);
    assertThat(selector.select("lip", "#FF0000", candidates)).hasSize(3);
    assertThat(selector.selectAll("lip", "#FF0000", List.of())).isEmpty();
  }

  @Test
  void withoutAReferenceColorEveryCompatibleColoredItemKeepsPouchOrder() {
    UUID first = UUID.fromString("00000000-0000-0000-0000-000000000009");
    UUID second = UUID.fromString("00000000-0000-0000-0000-000000000001");
    var candidates =
        List.of(
            candidate(first, "LIPSTICK", "#E00000"),
            candidate(UUID.randomUUID(), "EYESHADOW_PALETTE", "#FF0000"),
            candidate(second, "LIP_TINT", "#0000FF"));

    var all = selector.selectAll("lip", null, candidates);

    assertThat(all)
        .extracting(ranked -> ranked.candidate().pouchItemId())
        .containsExactly(first, second);
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
