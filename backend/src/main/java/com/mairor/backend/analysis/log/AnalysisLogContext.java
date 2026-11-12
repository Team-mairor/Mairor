package com.mairor.backend.analysis.log;

import com.mairor.backend.analysis.entity.AnalysisJob;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.slf4j.MDC;

/**
 * 분석 작업 로그 칸(MDC). 운영은 JSON 로그(logstash 형식)라 이 값들이 칸으로 나가고, 앱 서버 alloy 가 Loki structured metadata 로
 * 꺼내 Grafana 에서 작업 하나의 로그를 찾는다(S15P31A306-401).
 *
 * <ul>
 *   <li>{@value #ANALYSIS_JOB_ID}: BE 분석 작업 ID. 노트북 claim 의 {@code jobId}와 같다
 *   <li>{@value #VIDEO_ID}: YouTube 영상 ID. AI 로그의 같은 칸과 같은 값이라 영상 하나로 BE · AI 를 같이 찾는다
 *   <li>{@value #JOB_ID}: AI 가이드 작업 ID(AI 에 맡긴 뒤). AI 로그의 {@code job_id}와 같은 값이다
 * </ul>
 *
 * {@code try (var ignored = AnalysisLogContext.of(...))}로 쓰고, 닫으면 넣기 전 값으로 되돌린다(겹쳐 써도 바깥 값이 남는다).
 */
public final class AnalysisLogContext implements AutoCloseable {

  public static final String ANALYSIS_JOB_ID = "analysis_job_id";
  public static final String VIDEO_ID = "video_id";
  public static final String JOB_ID = "job_id";

  private final Map<String, String> previous = new LinkedHashMap<>();

  private AnalysisLogContext() {}

  /**
   * @param analysisJobId BE 분석 작업 ID. 모르면 {@code null}
   * @param youtubeVideoId YouTube 영상 ID. 모르면 {@code null}
   * @param aiJobId AI 가이드 작업 ID. 아직 맡기지 않았으면 {@code null}
   */
  public static AnalysisLogContext of(UUID analysisJobId, String youtubeVideoId, String aiJobId) {
    AnalysisLogContext context = new AnalysisLogContext();
    context.put(ANALYSIS_JOB_ID, analysisJobId == null ? null : analysisJobId.toString());
    context.put(VIDEO_ID, youtubeVideoId);
    context.put(JOB_ID, aiJobId);
    return context;
  }

  /** 작업의 세 칸. 영상을 읽으므로(지연 로딩) 트랜잭션 안에서 부른다. */
  public static AnalysisLogContext of(AnalysisJob job) {
    return of(job.getId(), job.getVideo().getYoutubeVideoId(), job.getAiJobId());
  }

  /** AI 에 맡겨 작업 ID 를 받았을 때 같은 범위에 더한다. 닫을 때 함께 되돌린다. */
  public AnalysisLogContext aiJob(String aiJobId) {
    put(JOB_ID, aiJobId);
    return this;
  }

  private void put(String key, String value) {
    if (value == null || value.isBlank()) {
      return;
    }
    if (!previous.containsKey(key)) {
      previous.put(key, MDC.get(key));
    }
    MDC.put(key, value);
  }

  @Override
  public void close() {
    previous.forEach(
        (key, value) -> {
          if (value == null) {
            MDC.remove(key);
          } else {
            MDC.put(key, value);
          }
        });
    previous.clear();
  }
}
