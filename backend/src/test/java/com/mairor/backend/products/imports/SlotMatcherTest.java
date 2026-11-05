package com.mairor.backend.products.imports;

import static com.mairor.backend.products.imports.ImportTestData.colorless;
import static com.mairor.backend.products.imports.ImportTestData.named;
import static com.mairor.backend.products.imports.ImportTestData.namedSlot;
import static com.mairor.backend.products.imports.ImportTestData.shade;
import static com.mairor.backend.products.imports.ImportTestData.unnamed;
import static com.mairor.backend.products.imports.ImportTestData.unnamedSlot;
import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.SlotOrderBasis;
import com.mairor.backend.products.imports.SlotMatcher.Kind;
import com.mairor.backend.products.imports.SlotMatcher.Pairing;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * 재수집한 호수의 칸을 기존 칸과 맞추는 규칙. 칸 수나 격자가 같다는 것은 같은 칸이라는 증거가 아니라서, 이름·번호 근거가 없으면 색까지 맞는지 확인하고, 그래도 확인할 수
 * 없으면 기존 칸을 그대로 둔다.
 */
class SlotMatcherTest {

  private static final double MAX_DELTA_E = 5.0;
  private static final SlotOrderBasis GRID = SlotOrderBasis.GRID;

  private static Pairing match(
      List<ProductShadeColor> existing,
      List<CollectedColor> incoming,
      SlotOrderBasis basis,
      boolean references) {
    return SlotMatcher.match(existing, incoming, basis, references, MAX_DELTA_E);
  }

  private static void assertKept(Pairing pairing) {
    assertThat(pairing.kind()).isEqualTo(Kind.KEPT);
    assertThat(pairing.pairs()).isEmpty();
    assertThat(pairing.reasons()).containsExactly(ImportReason.SHADE_LAYOUT_CHANGED);
  }

  // --- 비어 있는 쪽 ---

  @Test
  void noIncomingSlotsMeansNothingToDo() {
    ProductShade shade = shade("01");
    namedSlot(shade, 1, "Sand", "#D9B8A0");

    assertThat(match(shade.getColors(), List.of(), GRID, false).kind()).isEqualTo(Kind.NONE);
  }

  @Test
  void noExistingSlotsCreatesAllNewOnes() {
    Pairing pairing =
        match(List.of(), List.of(unnamed(1, "#111111"), unnamed(2, "#222222")), GRID, false);

    assertThat(pairing.kind()).isEqualTo(Kind.CREATE);
    assertThat(pairing.pairs()).hasSize(2).allSatisfy(p -> assertThat(p.existing()).isNull());
  }

  // --- 이름·번호 근거 ---

  @Test
  void namesMatchEvenWhenTheOrderChanged() {
    ProductShade shade = shade("01");
    ProductShadeColor sand = namedSlot(shade, 1, "Sand", "#D9B8A0");
    ProductShadeColor rose = namedSlot(shade, 2, "Rose", "#B76E79");

    Pairing pairing =
        match(
            shade.getColors(),
            List.of(named(1, " rose ", "#B76E79"), named(2, "SAND", "#D9B8A0")),
            GRID,
            true);

    assertThat(pairing.kind()).isEqualTo(Kind.MATCHED);
    assertThat(pairing.pairs()).extracting(SlotMatcher.Pair::existing).containsExactly(rose, sand);
    // 순서가 바뀌었으면 새 수집의 순서로 옮긴다
    assertThat(pairing.pairs()).extracting(SlotMatcher.Pair::sortOrder).containsExactly(1, 2);
  }

  @Test
  void nameEvidenceOverridesAChangedColor() {
    ProductShade shade = shade("01");
    ProductShadeColor sand = namedSlot(shade, 1, "Sand", "#D9B8A0");

    Pairing pairing = match(shade.getColors(), List.of(named(1, "Sand", "#0000FF")), GRID, true);

    assertThat(pairing.kind()).isEqualTo(Kind.MATCHED);
    assertThat(pairing.pairs().get(0).existing()).isSameAs(sand);
  }

  @Test
  void differentNameSetsDuplicatesOrPartialNamesAreNotMatched() {
    ProductShade shade = shade("01");
    namedSlot(shade, 1, "Sand", "#D9B8A0");
    namedSlot(shade, 2, "Rose", "#B76E79");

    // 이름 집합이 다르다
    assertKept(
        match(
            shade.getColors(),
            List.of(named(1, "Sand", "#D9B8A0"), named(2, "Plum", "#B76E79")),
            GRID,
            false));
    // 새 수집에 이름이 겹친다
    assertKept(
        match(
            shade.getColors(),
            List.of(named(1, "Sand", "#D9B8A0"), named(2, "sand", "#B76E79")),
            GRID,
            false));
    // 일부 칸에만 이름이 있으면 격자와 색이 같아도 위치로 맞추지 않는다
    assertKept(
        match(
            shade.getColors(),
            List.of(named(1, "Sand", "#D9B8A0"), unnamed(2, "#B76E79")),
            GRID,
            false));
  }

  @Test
  void modelCountedNumbersAreNotNameEvidence() {
    ProductShade shade = shade("01");
    // 이름 없는 칸(NONE)은 번호가 있어도 근거가 아니다
    unnamedSlot(shade, 1, "#D9B8A0");
    unnamedSlot(shade, 2, "#B76E79");

    Pairing pairing =
        match(
            shade.getColors(),
            List.of(
                ImportTestData.color(
                    1,
                    "1",
                    NameSource.NONE,
                    "#B76E79",
                    ColorSource.PRODUCT_PHOTO,
                    CollectedProduct.ShadeLink.OPTION_IMAGE,
                    0.9),
                ImportTestData.color(
                    2,
                    "2",
                    NameSource.NONE,
                    "#D9B8A0",
                    ColorSource.PRODUCT_PHOTO,
                    CollectedProduct.ShadeLink.OPTION_IMAGE,
                    0.9)),
            GRID,
            false);

    assertKept(pairing);
  }

  // --- 위치 근거(기존 칸에 HEX 가 있을 때) ---

  @Test
  void unnamedSlotsAreMatchedByPositionOnlyWhenEveryColorIsStillClose() {
    ProductShade shade = shade("01");
    ProductShadeColor first = unnamedSlot(shade, 1, "#C9707A");
    ProductShadeColor second = unnamedSlot(shade, 2, "#4A3427");

    Pairing pairing =
        match(
            shade.getColors(), List.of(unnamed(1, "#CA717B"), unnamed(2, "#4B3528")), GRID, false);

    assertThat(pairing.kind()).isEqualTo(Kind.MATCHED);
    assertThat(pairing.pairs())
        .extracting(SlotMatcher.Pair::existing)
        .containsExactly(first, second);
  }

  @Test
  void photoRotatedOnTheSameGridIsNotTrustedByCountAlone() {
    ProductShade shade = shade("01");
    unnamedSlot(shade, 1, "#C9707A");
    unnamedSlot(shade, 2, "#4A3427");
    unnamedSlot(shade, 3, "#E8D5B5");

    // 칸 수와 격자는 같지만 사진이 돌아가 색 순서가 거꾸로다
    Pairing pairing =
        match(
            shade.getColors(),
            List.of(unnamed(1, "#E8D5B5"), unnamed(2, "#4A3427"), unnamed(3, "#C9707A")),
            GRID,
            false);

    assertKept(pairing);
  }

  @Test
  void oneSlotOverTheLimitRejectsTheWholePositionMatch() {
    ProductShade shade = shade("01");
    unnamedSlot(shade, 1, "#C9707A");
    unnamedSlot(shade, 2, "#4A3427");

    assertKept(
        match(
            shade.getColors(), List.of(unnamed(1, "#C9707A"), unnamed(2, "#2B1B14")), GRID, false));
  }

  @Test
  void positionNeedsGridSameCountAndANewColorForEverySlot() {
    ProductShade shade = shade("01");
    unnamedSlot(shade, 1, "#C9707A");
    unnamedSlot(shade, 2, "#4A3427");

    assertKept(
        match(
            shade.getColors(),
            List.of(unnamed(1, "#C9707A"), unnamed(2, "#4A3427")),
            SlotOrderBasis.UNKNOWN,
            false));
    assertKept(match(shade.getColors(), List.of(unnamed(1, "#C9707A")), GRID, false));
    assertKept(
        match(
            shade.getColors(),
            List.of(unnamed(1, "#C9707A"), unnamed(2, "#4A3427"), unnamed(3, "#000000")),
            GRID,
            false));
    // 새 수집에서 한 칸의 색을 못 구하면 비교할 수 없다
    assertKept(match(shade.getColors(), List.of(unnamed(1, "#C9707A"), colorless(2)), GRID, false));
  }

  @Test
  void theColorLimitIsConfigurable() {
    ProductShade shade = shade("01");
    unnamedSlot(shade, 1, "#C9707A");
    unnamedSlot(shade, 2, "#4A3427");
    List<CollectedColor> slightlyDifferent = List.of(unnamed(1, "#D2707A"), unnamed(2, "#4A3427"));

    assertThat(SlotMatcher.match(shade.getColors(), slightlyDifferent, GRID, false, 0.1).kind())
        .isEqualTo(Kind.KEPT);
    assertThat(SlotMatcher.match(shade.getColors(), slightlyDifferent, GRID, false, 10.0).kind())
        .isEqualTo(Kind.MATCHED);
  }

  @Test
  void slotsWithoutAnyColorAreFilledByNameEvidence() {
    ProductShade shade = shade("01");
    ProductShadeColor sand =
        ImportTestData.slot(shade, 1, "Sand", NameSource.SITE_TEXT, null, null, null, null);

    Pairing pairing = match(shade.getColors(), List.of(named(1, "Sand", "#D9B8A0")), GRID, true);

    assertThat(pairing.kind()).isEqualTo(Kind.MATCHED);
    assertThat(pairing.pairs().get(0).existing()).isSameAs(sand);
  }

  @Test
  void slotsWithoutAnyColorAreNeverMatchedByPosition() {
    ProductShade shade = shade("01");
    ImportTestData.slot(shade, 1, null, NameSource.NONE, null, null, null, null);
    ImportTestData.slot(shade, 2, null, NameSource.NONE, null, null, null, null);

    Pairing referenced =
        match(shade.getColors(), List.of(unnamed(1, "#C9707A"), unnamed(2, "#4A3427")), GRID, true);

    // 참조가 있으면 이름 근거 없이는 바꾸지 않는다
    assertKept(referenced);
  }

  @Test
  void colorlessSlotsWithNoReferenceAreReplacedWithNewColorIds() {
    ProductShade shade = shade("01");
    ProductShadeColor a =
        ImportTestData.slot(shade, 1, null, NameSource.NONE, null, null, null, null);
    ProductShadeColor b =
        ImportTestData.slot(shade, 2, null, NameSource.NONE, null, null, null, null);

    Pairing pairing =
        match(
            shade.getColors(), List.of(unnamed(1, "#C9707A"), unnamed(2, "#4A3427")), GRID, false);

    assertThat(pairing.kind()).isEqualTo(Kind.REPLACE_ALL);
    assertThat(pairing.removed()).containsExactlyInAnyOrder(a, b);
    // 같은 칸이라고 주장하지 않으므로 새 칸으로 만든다
    assertThat(pairing.pairs()).hasSize(2).allSatisfy(p -> assertThat(p.existing()).isNull());
  }

  @Test
  void mixedColoredAndColorlessSlotsWithoutNamesKeepTheWholeShade() {
    ProductShade shade = shade("01");
    unnamedSlot(shade, 1, "#C9707A");
    ImportTestData.slot(shade, 2, null, NameSource.NONE, null, null, null, null);

    // 위치로 맞출 수 있어 보이는 색(#C9707A)이 있어도 색 없는 칸의 위치를 알 수 없으므로 호수 전체를 지킨다
    assertKept(
        match(
            shade.getColors(), List.of(unnamed(1, "#C9707A"), unnamed(2, "#4A3427")), GRID, false));
  }

  @Test
  void unusableOrRejectedColorsStillCountAsHavingAHex() {
    ProductShade shade = shade("01");
    ImportTestData.slot(
        shade,
        1,
        null,
        NameSource.NONE,
        "#C9707A",
        ColorSource.PRODUCT_PHOTO,
        ReviewStatus.BELOW_THRESHOLD,
        ImportTestData.T1);
    unnamedSlot(shade, 2, "#4A3427");

    // HEX 가 남아 있으므로 위치(ΔE) 기준으로 맞춘다. 색 없는 칸처럼 교체하지 않는다
    Pairing close =
        match(
            shade.getColors(), List.of(unnamed(1, "#CA717B"), unnamed(2, "#4A3427")), GRID, false);
    Pairing far =
        match(
            shade.getColors(), List.of(unnamed(1, "#2B1B14"), unnamed(2, "#4A3427")), GRID, false);

    assertThat(close.kind()).isEqualTo(Kind.MATCHED);
    assertKept(far);
  }

  // --- 단일 칸(기존·신규 모두 칸이 하나) ---

  @Test
  void aSingleSlotOnBothSidesIsTheSameSlotEvenWhenTheColorChangedALot() {
    ProductShade shade = shade("01");
    ProductShadeColor only = unnamedSlot(shade, 1, "#C9707A");

    // 사진 색을 더 믿을 수 있는 공식 색값으로 바꾸려는 경우처럼 색이 크게 달라도 칸은 같은 칸이다
    Pairing pairing =
        match(
            shade.getColors(),
            List.of(
                ImportTestData.color(
                    1,
                    null,
                    NameSource.NONE,
                    "#2B1B14",
                    ColorSource.SOURCE_VALUE,
                    CollectedProduct.ShadeLink.OPTION_IMAGE,
                    null)),
            SlotOrderBasis.UNKNOWN,
            false);

    assertThat(pairing.kind()).isEqualTo(Kind.MATCHED);
    assertThat(pairing.pairs().get(0).existing()).isSameAs(only);
  }

  @Test
  void aSingleColorlessSlotIsFilledEvenWhenReferencesExist() {
    ProductShade shade = shade("01");
    ProductShadeColor only =
        ImportTestData.slot(shade, 1, null, NameSource.NONE, null, null, null, null);

    // 위치가 헷갈릴 일이 없으므로 같은 colorId 에 색을 채운다. 참조가 있어도 칸을 지우고 새로 만들지 않는다
    Pairing pairing = match(shade.getColors(), List.of(unnamed(1, "#C9707A")), GRID, true);

    assertThat(pairing.kind()).isEqualTo(Kind.MATCHED);
    assertThat(pairing.pairs().get(0).existing()).isSameAs(only);
  }

  @Test
  void aSingleSlotWithOneNameAndOneWithoutIsStillTheSameSlot() {
    ProductShade shade = shade("01");
    ProductShadeColor only = namedSlot(shade, 1, "Sand", "#D9B8A0");

    Pairing pairing = match(shade.getColors(), List.of(unnamed(1, "#D9B8A0")), GRID, false);

    assertThat(pairing.kind()).isEqualTo(Kind.MATCHED);
    assertThat(pairing.pairs().get(0).existing()).isSameAs(only);
  }

  @Test
  void aSingleSlotWhoseNamesContradictIsNotTheSameSlot() {
    ProductShade shade = shade("01");
    namedSlot(shade, 1, "Sand", "#D9B8A0");

    // 둘 다 이름 근거가 있는데 이름이 다르면 다른 칸이라는 증거다
    assertKept(match(shade.getColors(), List.of(named(1, "Rose", "#D9B8A0")), GRID, false));
  }

  @Test
  void theSingleSlotRuleDoesNotApplyWhenEitherSideHasMoreSlots() {
    ProductShade shade = shade("01");
    unnamedSlot(shade, 1, "#C9707A");

    assertKept(
        match(
            shade.getColors(), List.of(unnamed(1, "#2B1B14"), unnamed(2, "#4A3427")), GRID, false));
  }
}
