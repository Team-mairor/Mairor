package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class CatalogImportRunTest {

  private static final Instant NOW = Instant.parse("2026-11-08T12:00:00Z");

  private static CatalogImportRun run() {
    return new CatalogImportRun("run-1", "OFFICIAL:etude.com", "0.1.0", "a.jsonl", NOW, NOW);
  }

  @Test
  void aNewRunIsRunningWithItsFirstHeartbeat() {
    CatalogImportRun run = run();

    assertThat(run.getStatus()).isEqualTo(ImportRunStatus.RUNNING);
    assertThat(run.getLastHeartbeatAt()).isEqualTo(NOW);
    assertThat(run.getFinishedAt()).isNull();
  }

  @Test
  void aHeartbeatMovesTheLastHeartbeat() {
    CatalogImportRun run = run();

    run.heartbeat(NOW.plusSeconds(30));

    assertThat(run.getLastHeartbeatAt()).isEqualTo(NOW.plusSeconds(30));
  }

  @Test
  void finishingRecordsTheStatusAndTheTime() {
    CatalogImportRun completed = run();
    completed.complete(NOW.plusSeconds(5));
    CatalogImportRun failed = run();
    failed.fail(NOW.plusSeconds(6));
    CatalogImportRun abandoned = run();
    abandoned.abandon(NOW.plusSeconds(7));

    assertThat(completed.getStatus()).isEqualTo(ImportRunStatus.COMPLETED);
    assertThat(completed.getFinishedAt()).isEqualTo(NOW.plusSeconds(5));
    assertThat(failed.getStatus()).isEqualTo(ImportRunStatus.FAILED);
    assertThat(abandoned.getStatus()).isEqualTo(ImportRunStatus.ABANDONED);
    assertThat(abandoned.getStatus().isFinished()).isTrue();
  }

  @Test
  void aFinishedRunCannotBeFinishedOrBeatAgain() {
    CatalogImportRun run = run();
    run.complete(NOW.plusSeconds(5));

    assertThatThrownBy(() -> run.heartbeat(NOW.plusSeconds(6)))
        .isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> run.abandon(NOW.plusSeconds(6)))
        .isInstanceOf(IllegalStateException.class);
    assertThat(run.getStatus()).isEqualTo(ImportRunStatus.COMPLETED);
  }

  @Test
  void aRunWithoutRecentHeartbeatsIsAbandonedOnlyWhileRunning() {
    CatalogImportRun run = run();
    Duration timeout = Duration.ofMinutes(10);

    assertThat(run.isAbandonedAt(NOW.plusSeconds(600), timeout)).isFalse();
    assertThat(run.isAbandonedAt(NOW.plusSeconds(601), timeout)).isTrue();
    run.complete(NOW.plusSeconds(1));
    assertThat(run.isAbandonedAt(NOW.plusSeconds(9999), timeout)).isFalse();
  }

  @Test
  void aBlankRunIdOrTooLongValuesAreRefused() {
    assertThatThrownBy(() -> new CatalogImportRun(" ", null, null, null, null, NOW))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new CatalogImportRun("x".repeat(101), null, null, null, null, NOW))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new CatalogImportRun("a", null, null, "f".repeat(201), null, NOW))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
