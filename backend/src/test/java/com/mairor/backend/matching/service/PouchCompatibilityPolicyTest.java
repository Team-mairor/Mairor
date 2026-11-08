package com.mairor.backend.matching.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class PouchCompatibilityPolicyTest {

  @Test
  void onlyExplicitMakeupTypePairsAreCompatible() {
    assertThat(PouchCompatibilityPolicy.supports("foundation", "CUSHION")).isTrue();
    assertThat(PouchCompatibilityPolicy.supports("foundation", "FOUNDATION")).isTrue();
    assertThat(PouchCompatibilityPolicy.supports("blush", "HIGHLIGHTER")).isFalse();
    assertThat(PouchCompatibilityPolicy.supports("contour", "CONTOUR")).isFalse();
    assertThat(PouchCompatibilityPolicy.supports("other", "LIP_TINT")).isFalse();
  }

  @Test
  void mapsSupportedMakeupToManualSelectionCategory() {
    assertThat(PouchCompatibilityPolicy.categoryFor("foundation")).isEqualTo("BASE");
    assertThat(PouchCompatibilityPolicy.categoryFor("eyeliner")).isEqualTo("EYE");
    assertThat(PouchCompatibilityPolicy.categoryFor("brow")).isEqualTo("BROW");
    assertThat(PouchCompatibilityPolicy.categoryFor("highlight")).isEqualTo("CHEEK");
    assertThat(PouchCompatibilityPolicy.categoryFor("lip")).isEqualTo("LIP");
    assertThat(PouchCompatibilityPolicy.categoryFor("unknown")).isNull();
  }
}
