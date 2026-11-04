package com.mairor.backend.analysis.worker;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.service.AiResultService;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.external.ai.AiProperties;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

/**
 * 콜백 시간 초과 감시가 늦은 작업을 AI 에 맡긴 시각으로 고르는지 실제 DB 로 확인한다. 진행 숫자를 저장해 {@code updated_at}이 최근이어도 맡긴 지 오래된
 * 작업은 고르고, 맡긴 시각이 빈 옛 행은 {@code updated_at}으로 고른다.
 *
 * <p>감시는 worker 프로파일에서만 뜨므로 실제 저장소로 직접 만든다. AI 는 모든 작업이 아직 진행 중이라고 답해, 고른 작업은 AI 에 묻고 두 배가 지난 작업만
 * 시간 초과로 끝낸다. 설정은 {@code AnalysisSchemaSqlTest}와 같게 둬서 컨텍스트를 함께 쓴다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class AiCallbackWatcherQueryTest {

  private static final Instant NOW = Instant.parse("2026-11-03T12:00:00Z");
  private static final Duration TIMEOUT = Duration.ofMinutes(60);

  @Autowired private JdbcTemplate jdbc;
  @Autowired private AnalysisJobRepository jobs;
  @Autowired private ObjectMapper objectMapper;

  private final AiGuideJobClient client = mock(AiGuideJobClient.class);
  private final AiResultService results = mock(AiResultService.class);
  private AiCallbackWatcher watcher;

  @BeforeEach
  void setUp() {
    watcher =
        new AiCallbackWatcher(
            jobs,
            client,
            results,
            new AiProperties(
                "http://ai:8000",
                "http://api:8080/api",
                Duration.ofSeconds(1),
                Duration.ofSeconds(1),
                Duration.ofHours(24),
                TIMEOUT,
                Duration.ofSeconds(60)),
            objectMapper,
            Clock.fixed(NOW, ZoneOffset.UTC));
    when(client.find(anyString())).thenReturn(Optional.of("{\"status\": \"RUNNING\"}"));
  }

  @Test
  void picksJobsByWhenTheyWereHandedToTheAiNotByTheirLastChange() {
    // 맡긴 지 61분, 진행 숫자를 방금 저장함 → 고른다 (두 배는 아님)
    job("RUNNING", "late-with-progress", minutesAgo(61), minutesAgo(1));
    // 맡긴 지 10분 → 고르지 않는다
    job("RUNNING", "recent", minutesAgo(10), minutesAgo(10));
    // 맡긴 지 121분, 진행 숫자를 방금 저장함 → 고르고 두 배가 지나 시간 초과
    job("RUNNING", "overdue-with-progress", minutesAgo(121), minutesAgo(1));

    watcher.check();

    verify(client).find("late-with-progress");
    verify(client, never()).find("recent");
    verify(client).find("overdue-with-progress");
    verify(results, never()).timeout(eq("late-with-progress"), anyString());
    verify(results).timeout(eq("overdue-with-progress"), anyString());
  }

  @Test
  void legacyRowsWithoutAHandOverTimeUseTheirLastChange() {
    job("RUNNING", "legacy-old", null, minutesAgo(61));
    job("RUNNING", "legacy-recent", null, minutesAgo(5));
    job("RUNNING", "legacy-overdue", null, minutesAgo(121));

    watcher.check();

    verify(client).find("legacy-old");
    verify(client, never()).find("legacy-recent");
    verify(results, never()).timeout(eq("legacy-old"), anyString());
    verify(results).timeout(eq("legacy-overdue"), anyString());
  }

  @Test
  void ignoresFinishedJobsAndJobsNotYetHandedToTheAi() {
    job("COMPLETED", "finished", minutesAgo(200), minutesAgo(200));
    job("FAILED", "failed", minutesAgo(200), minutesAgo(200));
    job("RUNNING", null, null, minutesAgo(200));

    watcher.check();

    verify(client, never()).find(anyString());
  }

  private static Instant minutesAgo(long minutes) {
    return NOW.minus(Duration.ofMinutes(minutes));
  }

  /** 영상마다 진행 중 작업은 하나뿐이라(uk_analysis_jobs_video_active) 작업마다 영상을 새로 만든다. */
  private void job(String status, String aiJobId, Instant aiRequestedAt, Instant updatedAt) {
    UUID videoId = UUID.randomUUID();
    jdbc.update(
        "insert into videos (id, youtube_video_id, title, channel_title, duration_seconds,"
            + " chapters, meta_refreshed_at, created_at, updated_at)"
            + " values (?, ?, '영상', '채널', 60, '[]'::jsonb, now(), now(), now())",
        videoId,
        videoId.toString().substring(0, 11));
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, ai_job_id,"
            + " ai_requested_at, attempt, created_at, updated_at)"
            + " values (?, ?, ?, 'BUILDING_GUIDE', false, ?, ?, 1, ?, ?)",
        UUID.randomUUID(),
        videoId,
        status,
        aiJobId,
        aiRequestedAt == null ? null : Timestamp.from(aiRequestedAt),
        Timestamp.from(updatedAt),
        Timestamp.from(updatedAt));
  }
}
