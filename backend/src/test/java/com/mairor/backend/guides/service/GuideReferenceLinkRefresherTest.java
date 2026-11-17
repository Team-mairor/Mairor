package com.mairor.backend.guides.service;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class GuideReferenceLinkRefresherTest {

  private static final Instant START = Instant.parse("2026-11-17T00:00:00Z");

  private final GuideReferenceLinkReconciliationDispatcher dispatcher =
      mock(GuideReferenceLinkReconciliationDispatcher.class);
  private final UUID guideId = UUID.randomUUID();

  private static GuideStepProductLink link(ReferenceMatchLevel level, ReferenceMatchReason reason) {
    GuideStepProductLink link = mock(GuideStepProductLink.class);
    when(link.getMatchLevel()).thenReturn(level);
    when(link.getReasonCode()).thenReturn(reason);
    return link;
  }

  private GuideReferenceLinkRefresher refresherAt(Instant... instants) {
    Clock clock = mock(Clock.class);
    var stubbing = when(clock.instant());
    for (Instant instant : instants) {
      stubbing = stubbing.thenReturn(instant);
    }
    return new GuideReferenceLinkRefresher(null, null, dispatcher, null, clock);
  }

  private static Clock fixed() {
    return Clock.fixed(START, ZoneOffset.UTC);
  }

  @Test
  void reschedulesWhenAStepStoppedBecauseTheCatalogLacksTheProduct() {
    var refresher = new GuideReferenceLinkRefresher(null, null, dispatcher, null, fixed());

    refresher.refreshIfNeeded(
        guideId,
        List.of("s1", "s2"),
        Map.of(
            "s1", link(ReferenceMatchLevel.SLOT, null),
            "s2", link(ReferenceMatchLevel.NONE, ReferenceMatchReason.PRODUCT_NOT_FOUND)));

    verify(dispatcher).scheduleAfterCommit(guideId);
  }

  @Test
  void reschedulesWhenAStepHasNoLinkYet() {
    var refresher = new GuideReferenceLinkRefresher(null, null, dispatcher, null, fixed());

    refresher.refreshIfNeeded(guideId, List.of("s1"), Map.of());

    verify(dispatcher).scheduleAfterCommit(guideId);
  }

  @Test
  void doesNothingWhenEveryStepIsLinkedToASlotOrCannotBeLinkedAtAll() {
    var refresher = new GuideReferenceLinkRefresher(null, null, dispatcher, null, fixed());

    refresher.refreshIfNeeded(
        guideId,
        List.of("s1", "s2", "s3"),
        Map.of(
            "s1", link(ReferenceMatchLevel.SLOT, null),
            "s2", link(ReferenceMatchLevel.NONE, ReferenceMatchReason.CATEGORY_UNSUPPORTED),
            "s3", link(ReferenceMatchLevel.NONE, ReferenceMatchReason.PRODUCT_NOT_PROVIDED)));

    verify(dispatcher, never()).scheduleAfterCommit(guideId);
  }

  @Test
  void schedulesAGuideOnlyOncePerInterval() {
    var refresher =
        refresherAt(
            START,
            START.plus(GuideReferenceLinkRefresher.MIN_INTERVAL).minusSeconds(1),
            START.plus(GuideReferenceLinkRefresher.MIN_INTERVAL));
    Map<String, GuideStepProductLink> links =
        Map.of("s1", link(ReferenceMatchLevel.NONE, ReferenceMatchReason.SHADE_NOT_FOUND));

    refresher.refreshIfNeeded(guideId, List.of("s1"), links);
    refresher.refreshIfNeeded(guideId, List.of("s1"), links);
    verify(dispatcher, times(1)).scheduleAfterCommit(guideId);

    refresher.refreshIfNeeded(guideId, List.of("s1"), links);
    verify(dispatcher, times(2)).scheduleAfterCommit(guideId);
  }
}
