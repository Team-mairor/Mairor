package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class CatalogCollectRequestTest {

  private static final Instant NOW = Instant.parse("2026-11-12T12:00:00Z");

  private static CatalogCollectRequest byName() {
    return new CatalogCollectRequest(
        CollectTrigger.USER, "key", "LIP", "LIP_TINT", "롬앤", "쥬시 틴트", null, null);
  }

  @Test
  void aNewRequestIsQueuedWithItsOwnJobId() {
    CatalogCollectRequest request = byName();

    assertThat(request.getId()).isNotNull();
    assertThat(request.getStatus()).isEqualTo(CollectRequestStatus.QUEUED);
    assertThat(request.isNew()).isTrue();
    assertThat(request.getFinishedAt()).isNull();
  }

  @Test
  void aRequestNeedsExactlyOneOfNameAndUrl() {
    assertThatThrownBy(
            () ->
                new CatalogCollectRequest(
                    CollectTrigger.USER, "k", null, null, "롬앤", "틴트", "https://a/p", null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                new CatalogCollectRequest(
                    CollectTrigger.USER, "k", null, null, "롬앤", null, null, null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void sendingCountsAttemptsAndKeepsTheRequestOpen() {
    CatalogCollectRequest request = byName();

    request.markSendFailed();
    request.markSent(NOW);

    assertThat(request.getSendAttempts()).isEqualTo(2);
    assertThat(request.getStatus()).isEqualTo(CollectRequestStatus.SENT);
    assertThat(request.getSentAt()).isEqualTo(NOW);
    assertThat(request.isOpen()).isTrue();
  }

  @Test
  void finishingClosesTheRequestOnce() {
    CatalogCollectRequest request = byName();
    UUID importRun = UUID.randomUUID();

    request.recordResult("COLLECTED", "20261112-000000-job-a.jsonl", importRun);
    request.finish(CollectRequestStatus.RESOLVED, null, NOW);

    assertThat(request.getImportRunId()).isEqualTo(importRun);
    assertThat(request.getFinishedAt()).isEqualTo(NOW);
    assertThatThrownBy(() -> request.finish(CollectRequestStatus.FAILED, "x", NOW))
        .isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> request.markSent(NOW)).isInstanceOf(IllegalStateException.class);
  }

  @Test
  void finishingNeedsAFinishedStatusAndCutsLongReasons() {
    CatalogCollectRequest request = byName();
    assertThatThrownBy(() -> request.finish(CollectRequestStatus.SENT, null, NOW))
        .isInstanceOf(IllegalArgumentException.class);

    request.finish(CollectRequestStatus.FAILED, "x".repeat(500), NOW);

    assertThat(request.getReason()).hasSize(CatalogCollectRequest.REASON_MAX_LENGTH);
  }

  @Test
  void aRequesterGivesThePouchItemAndItsUpdateTimeTogether() {
    assertThatThrownBy(
            () -> new CatalogCollectRequestUser(UUID.randomUUID(), UUID.randomUUID(), null, NOW))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void guideRequestsAreMadeOnlyThroughTheirFactoryAndNeedATargetBeyondProducts() {
    assertThatThrownBy(
            () ->
                new CatalogCollectRequest(
                    CollectTrigger.GUIDE, "k", "LIP", null, "롬앤", "틴트", null, null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                CatalogCollectRequest.forGuide(
                    CollectGap.SHADE_MISSING,
                    "k",
                    "LIP",
                    null,
                    "롬앤",
                    "틴트",
                    null,
                    "02",
                    CatalogCollectRequest.Target.NONE))
        .isInstanceOf(IllegalArgumentException.class);

    UUID product = UUID.randomUUID();
    CatalogCollectRequest request =
        CatalogCollectRequest.forGuide(
            CollectGap.COLOR_MISSING,
            "k",
            "LIP",
            "LIP_TINT",
            "롬앤",
            null,
            "https://a.example/p/1",
            "01",
            new CatalogCollectRequest.Target(product, UUID.randomUUID(), null, "3"));

    assertThat(request.getTrigger()).isEqualTo(CollectTrigger.GUIDE);
    assertThat(request.getTarget().productId()).isEqualTo(product);
    assertThat(request.getTarget().slotLabel()).isEqualTo("3");
  }
}
