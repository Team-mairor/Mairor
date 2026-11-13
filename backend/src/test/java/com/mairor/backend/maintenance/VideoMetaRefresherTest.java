package com.mairor.backend.maintenance;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.common.external.youtube.YouTubeClient;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.service.GuideReviewService;
import com.mairor.backend.guides.service.GuideReviewService.Decision;
import com.mairor.backend.maintenance.VideoMetaStore.StaleVideo;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class VideoMetaRefresherTest {

  private static final Instant NOW = Instant.parse("2026-11-13T19:30:00Z");

  private final VideoMetaStore store = mock(VideoMetaStore.class);
  private final YouTubeClient youTube = mock(YouTubeClient.class);
  private final GuideRepository guides = mock(GuideRepository.class);
  private final GuideReviewService reviews = mock(GuideReviewService.class);
  private final VideoMetaRefresher refresher =
      new VideoMetaRefresher(
          store,
          youTube,
          guides,
          reviews,
          JsonMapper.builder().build(),
          new MaintenanceProperties(
              Duration.ofDays(7), Duration.ofDays(30), Duration.ofDays(25), 200),
          Clock.fixed(NOW, ZoneOffset.UTC));

  @Test
  void aGuideThatCouldNotBeTakenDownIsLookedAtAgainTomorrowAndTheRestGoOn() {
    StaleVideo stuck = new StaleVideo(UUID.randomUUID(), "mntStuck001");
    StaleVideo gone = new StaleVideo(UUID.randomUUID(), "mntGone0002");
    when(store.staleBefore(any(), eq(200))).thenReturn(List.of(stuck, gone));
    when(youTube.videos(anyList())).thenReturn(List.of());
    Guide stuckGuide = guide();
    Guide goneGuide = guide();
    when(guides.findByVideoIdAndReviewStatus(stuck.id(), ReviewStatus.APPROVED))
        .thenReturn(Optional.of(stuckGuide));
    when(guides.findByVideoIdAndReviewStatus(gone.id(), ReviewStatus.APPROVED))
        .thenReturn(Optional.of(goneGuide));
    when(reviews.review(stuckGuide.getId(), Decision.REJECTED))
        .thenThrow(new IllegalStateException("DB 오류"));

    VideoMetaRefresher.Result result = refresher.run();

    assertThat(result).isEqualTo(new VideoMetaRefresher.Result(0, 1, 1, 1, false));
    verify(store, never()).markChecked(stuck.id(), NOW);
    verify(store).markChecked(gone.id(), NOW);
    verify(reviews).review(goneGuide.getId(), Decision.REJECTED);
  }

  private static Guide guide() {
    Guide guide = mock(Guide.class);
    when(guide.getId()).thenReturn(UUID.randomUUID());
    return guide;
  }
}
