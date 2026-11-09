package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class CatalogImportItemTest {

  private static final Instant NOW = Instant.parse("2026-11-08T12:00:00Z");

  private static CatalogImportItem item() {
    CatalogImportRun run = new CatalogImportRun("run-1", null, null, null, null, NOW);
    return new CatalogImportItem(run, "000001", "OFFICIAL:etude.com", "47508");
  }

  @Test
  void reasonsAreStoredSortedWithoutDuplicates() {
    CatalogImportItem item = item();

    item.recordResult(ImportItemOutcome.UPDATE, true, List.of("B", "A", "B"), null, 3, null);

    assertThat(item.getReasons()).isEqualTo("A,B");
    assertThat(item.getReasonCodes()).containsExactly("A", "B");
    assertThat(item.isPartial()).isTrue();
    assertThat(item.getColorsApplied()).isEqualTo(3);
  }

  @Test
  void noReasonsIsAnEmptyStringAndAnEmptyList() {
    CatalogImportItem item = item();

    item.recordResult(ImportItemOutcome.NEW, false, null, null, 0, null);

    assertThat(item.getReasons()).isEmpty();
    assertThat(item.getReasonCodes()).isEmpty();
  }

  @Test
  void reprocessingOverwritesThePreviousResult() {
    CatalogImportItem item = item();
    item.recordResult(ImportItemOutcome.FAILED, false, List.of("X"), null, 0, "오류");

    item.recordResult(ImportItemOutcome.NEW, false, List.of(), null, 2, null);

    assertThat(item.getOutcome()).isEqualTo(ImportItemOutcome.NEW);
    assertThat(item.getReasons()).isEmpty();
    assertThat(item.getMessage()).isNull();
  }

  @Test
  void aLongMessageIsTruncatedButTheOtherLimitsAreRefused() {
    CatalogImportItem item = item();

    item.recordResult(ImportItemOutcome.FAILED, false, List.of(), null, 0, "가".repeat(900));

    assertThat(item.getMessage()).hasSize(CatalogImportItem.MESSAGE_MAX_LENGTH).endsWith("…");
    assertThatThrownBy(
            () ->
                item.recordResult(
                    ImportItemOutcome.NEW, false, List.of("R".repeat(1001)), null, 0, null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () -> item.recordResult(ImportItemOutcome.NEW, false, List.of(), null, -1, null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void aBlankItemKeyOrTooLongSourceIsRefused() {
    CatalogImportRun run = new CatalogImportRun("run-1", null, null, null, null, NOW);

    assertThatThrownBy(() -> new CatalogImportItem(run, " ", null, null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new CatalogImportItem(run, "1", "s".repeat(101), null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void onlyAppliedOutcomesCountAsApplied() {
    assertThat(ImportItemOutcome.NEW.isApplied()).isTrue();
    assertThat(ImportItemOutcome.UPDATE.isApplied()).isTrue();
    for (ImportItemOutcome outcome :
        List.of(
            ImportItemOutcome.STALE,
            ImportItemOutcome.AMBIGUOUS,
            ImportItemOutcome.UNCLASSIFIED,
            ImportItemOutcome.INVALID,
            ImportItemOutcome.FAILED)) {
      assertThat(outcome.isApplied()).as(outcome.name()).isFalse();
    }
  }
}
