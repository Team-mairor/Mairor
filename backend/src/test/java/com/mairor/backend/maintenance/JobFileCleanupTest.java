package com.mairor.backend.maintenance;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.maintenance.JobFileStore.FinishedJob;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class JobFileCleanupTest {

  private static final Instant NOW = Instant.parse("2026-11-13T19:30:00Z");
  private static final Instant KEEP_FROM = NOW.minus(Duration.ofDays(7));

  private final JobFileStore store = mock(JobFileStore.class);
  private final ObjectStorage storage = mock(ObjectStorage.class);
  private final JobFileCleanup cleanup =
      new JobFileCleanup(
          store,
          storage,
          new MaintenanceProperties(
              Duration.ofDays(7), Duration.ofDays(30), Duration.ofDays(25), 200),
          Clock.fixed(NOW, ZoneOffset.UTC));

  @Test
  void aJobRetriedAfterTheListWasReadKeepsItsFiles() {
    FinishedJob retried = new FinishedJob(UUID.randomUUID(), UUID.randomUUID(), "mntRetry001");
    FinishedJob done = new FinishedJob(UUID.randomUUID(), UUID.randomUUID(), "mntDone0001");
    when(store.finishedBetween(NOW.minus(Duration.ofDays(30)), KEEP_FROM))
        .thenReturn(List.of(retried, done));
    when(store.releaseForCleanup(retried.jobId(), KEEP_FROM)).thenReturn(false);
    when(store.releaseForCleanup(done.jobId(), KEEP_FROM)).thenReturn(true);
    when(storage.deletePrefix(JobFileCleanup.jobPrefix(done))).thenReturn(2);

    JobFileCleanup.Result result = cleanup.run();

    verify(storage, never()).deletePrefix(JobFileCleanup.jobPrefix(retried));
    assertThat(result).isEqualTo(new JobFileCleanup.Result(1, 2, 0, 0));
  }
}
