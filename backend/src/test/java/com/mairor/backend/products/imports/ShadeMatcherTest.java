package com.mairor.backend.products.imports;

import static com.mairor.backend.products.imports.ImportTestData.collectedShade;
import static com.mairor.backend.products.imports.ImportTestData.hints;
import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.imports.CollectedProduct.CollectedShade;
import com.mairor.backend.products.imports.CollectedProduct.VariantHints;
import com.mairor.backend.products.imports.ShadeMatcher.Group;
import com.mairor.backend.products.imports.ShadeMatcher.Match;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ShadeMatcherTest {

  private static CollectedShade option(String id, String name, VariantHints hints) {
    return collectedShade(id, name, hints, List.of());
  }

  private static Product product() {
    ProductCategory lip = new ProductCategory("LIP", "립", true, true, 5);
    return new Product(new ProductType("LIP_TINT", lip, "립틴트", 3), "Brand", "Tint");
  }

  // --- 묶기 ---

  @Test
  void optionsWithTheSameKeyAndTheSameHintsAreMergedIntoOneShade() {
    List<Group> groups =
        ShadeMatcher.group(
            List.of(
                option("o-1", "[NEW] 01 코랄", hints("3g")),
                option("o-2", "01 코랄", hints("3g")),
                option("o-3", "01 코랄 +추가2종증정", hints("3g"))));

    assertThat(groups).hasSize(1);
    Group group = groups.get(0);
    // 지울 문구가 없던 옵션이 대표다
    assertThat(group.representative().sourceOptionId()).isEqualTo("o-2");
    assertThat(group.optionIds()).containsExactly("o-2", "o-1", "o-3");
    assertThat(group.mergeHeld()).isFalse();
  }

  @Test
  void whenEveryOptionHasAPhraseTheFirstOneIsTheRepresentative() {
    List<Group> groups =
        ShadeMatcher.group(
            List.of(
                option("o-1", "[NEW] 01 코랄", hints("3g")),
                option("o-2", "[BEST] 01 코랄", hints("3g"))));

    assertThat(groups).hasSize(1);
    assertThat(groups.get(0).representative().sourceOptionId()).isEqualTo("o-1");
  }

  @Test
  void aConflictSignalKeepsOptionsApart() {
    for (VariantHints other :
        List.of(
            hints("5g"),
            new VariantHints("3g", "세트", null, null, null),
            new VariantHints("3g", null, "매트", null, null),
            new VariantHints("3g", null, null, Map.of("용량", "미니"), null),
            new VariantHints("3g", null, null, null, "12000"))) {
      List<Group> groups =
          ShadeMatcher.group(
              List.of(option("o-1", "01 코랄", hints("3g")), option("o-2", "[NEW] 01 코랄", other)));

      assertThat(groups).as(other.toString()).hasSize(2);
      assertThat(groups).allSatisfy(g -> assertThat(g.mergeHeld()).isTrue());
    }
  }

  @Test
  void missingHintsMeanUnknownNotNoConflict() {
    List<Group> groups =
        ShadeMatcher.group(
            List.of(option("o-1", "01 코랄", null), option("o-2", "[NEW] 01 코랄", null)));

    assertThat(groups).hasSize(2).allSatisfy(g -> assertThat(g.mergeHeld()).isTrue());
    // 한쪽만 없어도 합치지 않는다
    assertThat(
            ShadeMatcher.group(
                List.of(option("o-1", "01 코랄", hints("3g")), option("o-2", "[NEW] 01 코랄", null))))
        .hasSize(2);
  }

  @Test
  void aPriceDifferenceAloneStopsTheMergeButIsNotAProofOfADifferentShade() {
    List<Group> groups =
        ShadeMatcher.group(
            List.of(
                option("o-1", "01 코랄", new VariantHints(null, null, null, null, "10000")),
                option("o-2", "[NEW] 01 코랄", new VariantHints(null, null, null, null, "12000"))));

    // 합치지 않고 둘 다 따로 둔다(운영 확인용 사유)
    assertThat(groups).hasSize(2).allSatisfy(g -> assertThat(g.mergeHeld()).isTrue());
  }

  @Test
  void differentKeysAreNeverGrouped() {
    List<Group> groups =
        ShadeMatcher.group(
            List.of(
                option("o-1", "01 코랄", hints("3g")), option("o-2", "[한정 매트] 01 코랄", hints("3g"))));

    assertThat(groups).hasSize(2).allSatisfy(g -> assertThat(g.mergeHeld()).isFalse());
  }

  // --- 기존 호수와 맞추기 ---

  @Test
  void noExistingShadeMeansANewShade() {
    Group group = ShadeMatcher.group(List.of(option("o-1", "01 코랄", hints("3g")))).get(0);

    assertThat(ShadeMatcher.find(group, List.of())).isInstanceOf(ShadeMatcher.Create.class);
  }

  @Test
  void aShadeIsFoundByItsOptionIdAndNewMergedOptionsBecomeAliases() {
    Product product = product();
    ProductShade existing = product.addShade("01 코랄", 1, null);
    existing.changeSourceOptionId("o-2");
    Group group =
        ShadeMatcher.group(
                List.of(
                    option("o-2", "01 코랄", hints("3g")), option("o-9", "[NEW] 01 코랄", hints("3g"))))
            .get(0);

    Match match = ShadeMatcher.find(group, product.getShades());

    assertThat(match)
        .isInstanceOfSatisfying(
            ShadeMatcher.Update.class,
            u -> {
              assertThat(u.existing()).isSameAs(existing);
              assertThat(u.newPrimaryOptionId()).isNull();
              assertThat(u.addAliases()).containsExactly("o-9");
              assertThat(u.removeAliases()).isEmpty();
            });
  }

  @Test
  void whenTheOldRepresentativeDisappearsAnAliasKeepsTheShadeAndTheNewRepresentativeTakesOver() {
    Product product = product();
    ProductShade existing = product.addShade("01 코랄", 1, null);
    existing.changeSourceOptionId("old-main");
    existing.addOptionAlias("o-5");
    // 사이트에서 old-main 이 사라지고 o-5 와 o-6 만 남았다
    Group group =
        ShadeMatcher.group(
                List.of(
                    option("o-5", "01 코랄", hints("3g")), option("o-6", "[NEW] 01 코랄", hints("3g"))))
            .get(0);

    ShadeMatcher.Update update =
        (ShadeMatcher.Update) ShadeMatcher.find(group, product.getShades());

    assertThat(update.existing()).isSameAs(existing);
    assertThat(update.newPrimaryOptionId()).isEqualTo("o-5");
    // 옛 대표는 별칭이 되고, 대표가 된 값은 별칭에서 뺀다
    assertThat(update.addAliases()).containsExactlyInAnyOrder("old-main", "o-6");
    assertThat(update.removeAliases()).containsExactly("o-5");
  }

  @Test
  void optionsPointingAtTwoDifferentExistingShadesAreAmbiguous() {
    Product product = product();
    ProductShade first = product.addShade("01 코랄", 1, null);
    first.changeSourceOptionId("o-1");
    ProductShade second = product.addShade("02 체리", 2, null);
    second.changeSourceOptionId("o-2");
    Group group =
        ShadeMatcher.group(
                List.of(
                    option("o-1", "01 코랄", hints("3g")), option("o-2", "[NEW] 01 코랄", hints("3g"))))
            .get(0);

    assertThat(ShadeMatcher.find(group, product.getShades()))
        .isInstanceOf(ShadeMatcher.Ambiguous.class);
  }

  @Test
  void sameNameWithoutAMatchingOptionIsAmbiguousNotAutomaticallyLinked() {
    Product product = product();
    // 시드나 직접 넣은 호수(옵션 값 없음)
    product.addShade("01 코랄", 1, null);
    ProductShade withOtherOption = product.addShade("02 체리", 2, null);
    withOtherOption.changeSourceOptionId("other");

    Group sameNameNoOption =
        ShadeMatcher.group(List.of(option("o-1", "[NEW] 01 코랄", hints("3g")))).get(0);
    Group sameNameOtherOption =
        ShadeMatcher.group(List.of(option("o-9", "02 체리", hints("3g")))).get(0);

    assertThat(ShadeMatcher.find(sameNameNoOption, product.getShades()))
        .isInstanceOf(ShadeMatcher.Ambiguous.class);
    assertThat(ShadeMatcher.find(sameNameOtherOption, product.getShades()))
        .isInstanceOf(ShadeMatcher.Ambiguous.class);
  }

  @Test
  void aShadeWithAnUnrelatedNameIsNew() {
    Product product = product();
    product.addShade("01 코랄", 1, null);
    Group group = ShadeMatcher.group(List.of(option("o-3", "03 누드", hints("3g")))).get(0);

    assertThat(ShadeMatcher.find(group, product.getShades()))
        .isInstanceOf(ShadeMatcher.Create.class);
  }
}
