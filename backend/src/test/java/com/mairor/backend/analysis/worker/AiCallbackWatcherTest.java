package com.mairor.backend.analysis.worker;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.service.AiResultService;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.external.ai.AiProperties;
import com.mairor.backend.common.external.ai.AiServerException;
import java.time.Clock;
import java.time.Duration;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 콜백이 늦은 작업: AI 에 물어 끝났으면 반영, 없으면 시간 초과, 진행 중이면 두 배까지 기다림. */
class AiCallbackWatcherTest {

  private final AiGuideJobClient client = mock(AiGuideJobClient.class);
  private final AiResultService results = mock(AiResultService.class);
  private final AiCallbackWatcher watcher =
      new AiCallbackWatcher(
          mock(AnalysisJobRepository.class),
          client,
          results,
          new AiProperties(
              "http://ai:8000",
              "http://api:8080/api",
              Duration.ofSeconds(1),
              Duration.ofSeconds(1),
              Duration.ofHours(24),
              Duration.ofMinutes(60),
              Duration.ofSeconds(60),
              null),
          JsonMapper.builder().build(),
          Clock.systemUTC());

  @Test
  void jobTheAiNoLongerHasTimesOut() {
    when(client.find("gone")).thenReturn(Optional.empty());

    watcher.checkOne("gone", false);

    verify(results).timeout(eq("gone"), argThat(r -> r.contains("AI 서버에 작업이 없습니다")));
  }

  @Test
  void finishedJobWhoseCallbackWasLostIsApplied() {
    when(client.find("lost"))
        .thenReturn(
            Optional.of(
                """
                {"jobId": "lost", "videoId": "v", "status": "COMPLETED", "guide": {"steps": []},
                 "area": null, "error": null, "progress": null,
                 "callback": {"attempts": 4, "delivered": false, "lastError": "timeout"}}
                """));

    watcher.checkOne("lost", false);

    verify(results).apply(argThat(r -> r.jobId().equals("lost") && r.status().equals("COMPLETED")));
    verify(results, never()).timeout(anyString(), anyString());
  }

  @Test
  void runningJobWaitsUntilOverdue() {
    when(client.find("slow"))
        .thenReturn(Optional.of("{\"jobId\": \"slow\", \"status\": \"RUNNING\"}"));

    watcher.checkOne("slow", false);
    verify(results, never()).timeout(anyString(), anyString());

    watcher.checkOne("slow", true);
    verify(results).timeout(eq("slow"), anyString());
  }

  @Test
  void unreachableAiWaitsUntilOverdue() {
    when(client.find(any())).thenThrow(new AiServerException("연결 실패", null, null));

    watcher.checkOne("down", false);
    verify(results, never()).timeout(anyString(), anyString());

    watcher.checkOne("down", true);
    verify(results).timeout(eq("down"), anyString());
  }
}
