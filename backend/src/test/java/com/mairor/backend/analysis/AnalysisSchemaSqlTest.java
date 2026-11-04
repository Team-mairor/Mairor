package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.LlmCall;
import com.mairor.backend.analysis.entity.LlmCallStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.repository.LlmCallRepository;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import jakarta.persistence.EntityManager;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 스키마 SQL({@code db/schema/analysis.sql})이 영상·분석 작업·가이드·LLM 호출 엔티티와 맞는지 확인한다.
 *
 * <p>운영과 같은 조건이다. 빈 DB 에 SQL 을 먼저 적용하고 {@code ddl-auto=validate} 로 앱을 띄운다. 엔티티와 SQL 이 어긋나면 앱이 뜨지 않아
 * 실패한다. 설정은 {@code UsersSchemaSqlTest}와 같게 둬서 컨텍스트를 함께 쓴다.
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
class AnalysisSchemaSqlTest {

  @Autowired private JdbcTemplate jdbc;
  @Autowired private EntityManager em;
  @Autowired private VideoRepository videos;
  @Autowired private AnalysisJobRepository jobs;
  @Autowired private GuideRepository guides;
  @Autowired private LlmCallRepository llmCalls;

  @Test
  void entitiesValidateAgainstTheSqlSchema() {
    // 앱이 ddl-auto=validate 로 기동했다는 것 자체가 엔티티와 SQL 이 맞다는 뜻이다
    for (String table : List.of("videos", "analysis_jobs", "guides", "llm_calls")) {
      assertThat(jdbc.queryForObject("select count(*) from " + table, Integer.class))
          .as(table)
          .isZero();
    }
  }

  @Test
  void entitiesRoundTripIncludingJsonbColumns() {
    Video video =
        videos.save(
            new Video(
                "VxAXD6PP76I",
                "완성도 up! 요즘 진짜 예뻐진 메이크업",
                "GO지승",
                1858,
                "https://i.ytimg.com/vi/VxAXD6PP76I/hqdefault.jpg",
                Instant.parse("2026-03-01T00:00:00Z"),
                "[{\"startSeconds\": 0, \"label\": \"시작\"}]",
                Instant.parse("2026-11-03T00:00:00Z")));
    video.attachSource("videos/VxAXD6PP76I/source.mp4", 1920, 1080, 60.0, 1858.2);
    AnalysisJob job = jobs.save(new AnalysisJob(video, null));
    Guide guide = guides.save(new Guide(job, 1, "{\"videoId\": \"VxAXD6PP76I\", \"steps\": []}"));
    LlmCall call =
        llmCalls.save(
            new LlmCall(
                job.getId(),
                "GEMINI",
                "gemini-2.5-flash",
                "STEP_EXTRACTION",
                LlmCallStatus.SUCCEEDED,
                540000,
                8000,
                123456,
                null,
                "{\"steps\": []}"));
    em.flush();
    em.clear();

    Video savedVideo = videos.findByYoutubeVideoId("VxAXD6PP76I").orElseThrow();
    assertThat(savedVideo.getSourceFps()).isEqualTo(60.0);
    assertThat(savedVideo.getChapters()).contains("시작");
    AnalysisJob savedJob = jobs.findById(job.getId()).orElseThrow();
    assertThat(savedJob.getStatus()).isEqualTo(AnalysisStatus.PENDING);
    assertThat(savedJob.getProgressStage()).isEqualTo(ProgressStage.QUEUED);
    assertThat(savedJob.getAttempt()).isEqualTo(1);
    Guide savedGuide = guides.findByAnalysisJobId(job.getId()).orElseThrow();
    assertThat(savedGuide.getReviewStatus()).isEqualTo(ReviewStatus.NOT_READY);
    assertThat(savedGuide.getGuideInput()).contains("VxAXD6PP76I");
    assertThat(savedGuide.getExplanation()).isNull();
    assertThat(llmCalls.findByAnalysisJobIdOrderByCreatedAtAsc(job.getId()))
        .extracting(LlmCall::getId)
        .containsExactly(call.getId());

    // jsonb 로 저장됐는지: 문자열이 아니라 JSON 으로 읽힌다
    assertThat(
            jdbc.queryForObject(
                "select jsonb_typeof(guide_input) from guides where id = ?",
                String.class,
                guide.getId()))
        .isEqualTo("object");
    assertThat(
            jdbc.queryForObject(
                "select chapters -> 0 ->> 'label' from videos where id = ?",
                String.class,
                video.getId()))
        .isEqualTo("시작");
  }

  @Test
  void videoColumnsHaveTheExpectedNullabilityAndLength() {
    List<Map<String, Object>> columns = columns("videos");

    assertThat(columns)
        .extracting(c -> c.get("column_name"))
        .containsExactlyInAnyOrder(
            "id",
            "youtube_video_id",
            "title",
            "channel_title",
            "duration_seconds",
            "thumbnail_url",
            "published_at",
            "chapters",
            "source_object_key",
            "source_width",
            "source_height",
            "source_fps",
            "source_duration_seconds",
            "meta_refreshed_at",
            "created_at",
            "updated_at");
    for (String optional :
        List.of(
            "thumbnail_url",
            "published_at",
            "source_object_key",
            "source_width",
            "source_height",
            "source_fps",
            "source_duration_seconds")) {
      assertThat(column(columns, optional).get("is_nullable")).as(optional).isEqualTo("YES");
    }
    assertThat(column(columns, "youtube_video_id").get("character_maximum_length"))
        .isEqualTo(Video.YOUTUBE_VIDEO_ID_MAX_LENGTH);
    assertThat(column(columns, "title").get("character_maximum_length"))
        .isEqualTo(Video.TITLE_MAX_LENGTH);
    assertThat(column(columns, "chapters").get("data_type")).isEqualTo("jsonb");
  }

  @Test
  void guideJsonColumnsAreJsonb() {
    List<Map<String, Object>> columns = columns("guides");

    for (String json : List.of("guide_input", "explanation", "area")) {
      assertThat(column(columns, json).get("data_type")).as(json).isEqualTo("jsonb");
    }
    assertThat(column(columns, "guide_input").get("is_nullable")).isEqualTo("NO");
    for (String optional : List.of("explanation", "area", "mesh_version", "frames_manifest_key")) {
      assertThat(column(columns, optional).get("is_nullable")).as(optional).isEqualTo("YES");
    }
  }

  @Test
  void analysisJobColumnsHaveTheExpectedNullability() {
    List<Map<String, Object>> columns = columns("analysis_jobs");

    for (String optional :
        List.of(
            "progress_percent",
            "failure_code",
            "failure_message",
            "ai_job_id",
            "ai_requested_at",
            "ai_progress",
            "requested_by",
            "started_at",
            "finished_at")) {
      assertThat(column(columns, optional).get("is_nullable")).as(optional).isEqualTo("YES");
    }
    assertThat(column(columns, "ai_job_id").get("character_maximum_length"))
        .isEqualTo(AnalysisJob.AI_JOB_ID_MAX_LENGTH);
    assertThat(column(columns, "ai_progress").get("data_type")).isEqualTo("jsonb");
  }

  @Test
  void aiRequestTimeAndProgressRoundTrip() {
    Video video =
        videos.save(
            new Video(
                "eFzG30avtOI",
                "영상",
                "채널",
                525,
                null,
                null,
                "[]",
                Instant.parse("2026-11-03T00:00:00Z")));
    AnalysisJob job = jobs.save(new AnalysisJob(video, null));
    Instant handedOver = Instant.parse("2026-11-03T01:00:00Z");
    job.start(handedOver);
    job.advanceTo(ProgressStage.BUILDING_GUIDE);
    job.awaitAi("8728c83b0d124c74a23863a50d4d7c0c", handedOver);
    job.recordAiProgress(
        "{\"explanation\": {\"done\": 19, \"total\": 19}, \"frames\": {\"done\": 840, \"total\":"
            + " 2000}, \"landmarks\": {\"done\": 0, \"total\": 2000}, \"area\": {\"done\": 0,"
            + " \"total\": 19}}");
    em.flush();
    em.clear();

    AnalysisJob saved = jobs.findById(job.getId()).orElseThrow();
    assertThat(saved.getAiRequestedAt()).isEqualTo(handedOver);
    assertThat(
            jdbc.queryForObject(
                "select ai_progress -> 'frames' ->> 'done' from analysis_jobs where id = ?",
                String.class,
                job.getId()))
        .isEqualTo("840");
  }

  /**
   * {@code ai_requested_at} 칸이 생기기 전에 AI 에 맡긴 작업(칸이 빔)도 진행 숫자를 여러 번 저장하는 동안 시간 초과 기준이 첫 저장 전 {@code
   * updated_at}으로 고정된다.
   */
  @Test
  void legacyAwaitingJobKeepsItsTimeoutBaselineWhileProgressIsSaved() {
    Video video =
        videos.save(
            new Video(
                "eFzG30avtOI",
                "영상",
                "채널",
                525,
                null,
                null,
                "[]",
                Instant.parse("2026-11-03T00:00:00Z")));
    em.flush();
    UUID jobId = UUID.randomUUID();
    Instant lastChange = Instant.parse("2026-11-03T01:00:00Z");
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, ai_job_id,"
            + " attempt, created_at, updated_at)"
            + " values (?, ?, 'RUNNING', 'BUILDING_GUIDE', false, 'legacy-ai-job', 1, ?, ?)",
        jobId,
        video.getId(),
        Timestamp.from(lastChange),
        Timestamp.from(lastChange));

    for (int done = 1; done <= 3; done++) {
      AnalysisJob job = jobs.findById(jobId).orElseThrow();
      assertThat(job.recordAiProgress("{\"explanation\": {\"done\": " + done + ", \"total\": 19}}"))
          .isTrue();
      em.flush();
      em.clear();
    }

    Map<String, Object> row =
        jdbc.queryForMap(
            "select ai_requested_at, updated_at, ai_progress -> 'explanation' ->> 'done' as done"
                + " from analysis_jobs where id = ?",
            jobId);
    assertThat(((Timestamp) row.get("ai_requested_at")).toInstant()).isEqualTo(lastChange);
    assertThat(((Timestamp) row.get("updated_at")).toInstant()).isAfter(lastChange);
    assertThat(row.get("done")).isEqualTo("3");
  }

  private List<Map<String, Object>> columns(String table) {
    return jdbc.queryForList(
        "select column_name, is_nullable, character_maximum_length, data_type "
            + "from information_schema.columns where table_name = ?",
        table);
  }

  private static Map<String, Object> column(List<Map<String, Object>> columns, String name) {
    return columns.stream()
        .filter(c -> name.equals(c.get("column_name")))
        .findFirst()
        .orElseThrow();
  }
}
