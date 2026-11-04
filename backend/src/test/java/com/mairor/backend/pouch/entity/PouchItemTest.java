package com.mairor.backend.pouch.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class PouchItemTest {

  @Test
  void displayTextIsTrimmedButOnlyComparisonKeysCollapseAndCompose() {
    PouchItem item = manual("\u00a0 A  B \u3000", " E\u0301  Lip\t", "\t Rose  01 ");

    assertThat(item.getBrand()).isEqualTo("A  B");
    assertThat(item.getName()).isEqualTo("E\u0301  Lip");
    assertThat(item.getShadeName()).isEqualTo("Rose  01");
    assertThat(item.getBrandNormalized()).isEqualTo("a b");
    assertThat(item.getNameNormalized()).isEqualTo("é lip");
    assertThat(item.getShadeNameNormalized()).isEqualTo("rose 01");
  }

  @Test
  void maximumLengthTextWithEdgeWhitespaceFitsItsStorageColumn() {
    PouchItem item =
        manual(
            " " + "B".repeat(100) + " ",
            "\t" + "N".repeat(200) + "\u3000",
            " " + "S".repeat(100) + " ");

    assertThat(item.getBrand()).hasSize(100);
    assertThat(item.getName()).hasSize(200);
    assertThat(item.getShadeName()).hasSize(100);
    assertThatThrownBy(() -> manual("B".repeat(101), "Name", null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> manual("Brand", "N".repeat(201), null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> manual("Brand", "Name", "S".repeat(101)))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void missingAndWhitespaceOnlyShadesUseOneNonNullComparisonKey() {
    for (String shade : new String[] {null, "", "\t\u00a0\u3000"}) {
      PouchItem item = manual("Brand", "Name", shade);
      assertThat(item.getShadeName()).isNull();
      assertThat(item.getShadeNameNormalized()).isEmpty();
      assertThat(item.getColor()).isNull();
      assertThat(item.getColorSource()).isEqualTo("NONE");
    }
    assertThatThrownBy(() -> manual("\u00a0", "Name", null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void registrationModeRejectsInconsistentIdsAndColorOrigins() {
    assertThatThrownBy(
            () ->
                new PouchItem(
                    UUID.randomUUID(),
                    RegistrationMode.MANUAL,
                    UUID.randomUUID(),
                    null,
                    "LIP",
                    "LIPSTICK",
                    "Brand",
                    "Name",
                    null,
                    null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                new PouchItem(
                    UUID.randomUUID(),
                    RegistrationMode.CATALOG,
                    null,
                    null,
                    "LIP",
                    "LIPSTICK",
                    "Brand",
                    "Name",
                    null,
                    null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                new PouchItem(
                    UUID.randomUUID(),
                    RegistrationMode.MANUAL,
                    null,
                    null,
                    "LIP",
                    "LIPSTICK",
                    "Brand",
                    "Name",
                    null,
                    PouchColor.catalog("#123456", false)))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void colorsPreserveOriginAndEstimateAndNormalizeHex() {
    assertThat(PouchColor.userInput("#aabbcc")).isEqualTo(PouchColor.userInput("#AABBCC"));
    assertThat(PouchColor.userInput("#aabbcc").isEstimated()).isTrue();
    assertThat(PouchColor.catalog("#123456", false).isEstimated()).isFalse();
    assertThat(PouchColor.catalog("#123456", false))
        .isNotEqualTo(PouchColor.catalog("#123456", true));
    assertThat(PouchColor.catalog("#123456", true)).isNotEqualTo(PouchColor.userInput("#123456"));
    assertThatThrownBy(() -> PouchColor.userInput("123456"))
        .isInstanceOf(IllegalArgumentException.class);
  }

  private PouchItem manual(String brand, String name, String shade) {
    return new PouchItem(
        UUID.randomUUID(),
        RegistrationMode.MANUAL,
        null,
        null,
        "LIP",
        "LIPSTICK",
        brand,
        name,
        shade,
        null);
  }
}
