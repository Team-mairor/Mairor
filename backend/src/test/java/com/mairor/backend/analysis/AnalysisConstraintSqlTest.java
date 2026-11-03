package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.LlmCall;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.videos.entity.Video;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 스키마 SQL({@code db/schema/analysis.sql})의 제약과 인덱스를 SQL 로 직접 넣어 확인한다. 특히 JPA 로 표현할 수 없어 SQL 에만 있는
 * 부분 유일 인덱스 두 개(같은 영상 진행 작업 하나, 같은 영상 공개 가이드 하나)를 본다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class AnalysisConstraintSqlTest {

  private static final String VIDEO_ID = "00000000-0000-4000-8000-0000000000a1";
  private static final String JOB_1 = "00000000-0000-4000-8000-0000000000b1";
  private static final String JOB_2 = "00000000-0000-4000-8000-0000000000b2";
  private static final String JOB_3 = "00000000-0000-4000-8000-0000000000b3";

  private static final String INSERT_JOB =
      "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, attempt,"
          + " created_at, updated_at) values (?::uuid, ?::uuid, ?, ?, false, 1, now(), now())";
  private static final String INSERT_GUIDE =
      "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input,"
          + " created_at, updated_at)"
          + " values (gen_random_uuid(), ?::uuid, ?::uuid, ?, ?, '{}'::jsonb, now(), now())";

  @Autowired private JdbcTemplate jdbc;

  @BeforeEach
  void setUp() {
    jdbc.update(
        "insert into videos (id, youtube_video_id, title, channel_title, duration_seconds,"
            + " chapters, meta_refreshed_at, created_at, updated_at)"
            + " values (?::uuid, 'VxAXD6PP76I', '영상', '채널', 1858, '[]'::jsonb, now(), now(),"
            + " now())",
        VIDEO_ID);
  }

  // --- 제약 이름 ---

  @Test
  void constraintsUseTheNamesTheCodeDependsOn() {
    assertThat(constraints("videos")).contains("videos_pkey", Video.YOUTUBE_VIDEO_ID_UNIQUE);
    assertThat(constraints("analysis_jobs"))
        .contains(
            "analysis_jobs_pkey",
            AnalysisJob.VIDEO_FK,
            AnalysisJob.REQUESTED_BY_FK,
            AnalysisJob.AI_JOB_ID_UNIQUE);
    assertThat(constraints("guides"))
        .contains(
            "guides_pkey",
            Guide.VIDEO_FK,
            Guide.ANALYSIS_JOB_FK,
            Guide.REVIEWED_BY_FK,
            Guide.ANALYSIS_JOB_UNIQUE,
            Guide.VIDEO_VERSION_UNIQUE);
    assertThat(constraints("llm_calls")).contains("llm_calls_pkey", LlmCall.ANALYSIS_JOB_FK);
    assertThat(indexes("analysis_jobs")).contains(AnalysisJob.VIDEO_ACTIVE_UNIQUE);
    assertThat(indexes("guides")).contains(Guide.VIDEO_APPROVED_UNIQUE);
  }

  // --- 영상 ---

  @Test
  void sameYoutubeVideoIsOneRow() {
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "insert into videos (id, youtube_video_id, title, channel_title,"
                        + " duration_seconds, chapters, meta_refreshed_at, created_at, updated_at)"
                        + " values (gen_random_uuid(), 'VxAXD6PP76I', '영상', '채널', 1858,"
                        + " '[]'::jsonb, now(), now(), now())"))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(Video.YOUTUBE_VIDEO_ID_UNIQUE);
  }

  // --- 분석 작업 ---

  @Test
  void oneActiveJobPerVideo() {
    jdbc.update(INSERT_JOB, JOB_1, VIDEO_ID, "PENDING", "QUEUED");

    assertThatThrownBy(() -> jdbc.update(INSERT_JOB, JOB_2, VIDEO_ID, "RUNNING", "SEGMENTING"))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(AnalysisJob.VIDEO_ACTIVE_UNIQUE);
  }

  @Test
  void finishedJobsDoNotBlockANewJob() {
    jdbc.update(INSERT_JOB, JOB_1, VIDEO_ID, "FAILED", "EXTRACTING_STEPS");

    assertThatCode(() -> jdbc.update(INSERT_JOB, JOB_2, VIDEO_ID, "PENDING", "QUEUED"))
        .doesNotThrowAnyException();
  }

  // 제약 위반이 나면 같은 트랜잭션의 다음 문장이 막히므로, 위반은 테스트마다 한 번만 낸다

  @Test
  void statusOutsideTheSpecIsRejected() {
    assertThatThrownBy(() -> jdbc.update(INSERT_JOB, JOB_1, VIDEO_ID, "CANCELLED", "QUEUED"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("ck_analysis_jobs_status");
  }

  @Test
  void progressStageOutsideTheSpecIsRejected() {
    assertThatThrownBy(() -> jdbc.update(INSERT_JOB, JOB_1, VIDEO_ID, "PENDING", "UPLOADING"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("ck_analysis_jobs_progress_stage");
  }

  // --- 가이드 ---

  @Test
  void oneApprovedGuidePerVideo() {
    jdbc.update(INSERT_JOB, JOB_1, VIDEO_ID, "COMPLETED", "DONE");
    jdbc.update(INSERT_JOB, JOB_2, VIDEO_ID, "COMPLETED", "DONE");
    jdbc.update(INSERT_JOB, JOB_3, VIDEO_ID, "COMPLETED", "DONE");
    jdbc.update(INSERT_GUIDE, VIDEO_ID, JOB_1, 1, "APPROVED");
    // 공개가 아닌 가이드는 같은 영상에 여러 개 있어도 된다
    assertThatCode(() -> jdbc.update(INSERT_GUIDE, VIDEO_ID, JOB_2, 2, "PENDING"))
        .doesNotThrowAnyException();

    assertThatThrownBy(() -> jdbc.update(INSERT_GUIDE, VIDEO_ID, JOB_3, 3, "APPROVED"))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(Guide.VIDEO_APPROVED_UNIQUE);
  }

  @Test
  void oneGuidePerJob() {
    jdbc.update(INSERT_JOB, JOB_1, VIDEO_ID, "COMPLETED", "DONE");
    jdbc.update(INSERT_GUIDE, VIDEO_ID, JOB_1, 1, "PENDING");

    assertThatThrownBy(() -> jdbc.update(INSERT_GUIDE, VIDEO_ID, JOB_1, 2, "PENDING"))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(Guide.ANALYSIS_JOB_UNIQUE);
  }

  @Test
  void reviewStatusOutsideTheSpecIsRejected() {
    jdbc.update(INSERT_JOB, JOB_1, VIDEO_ID, "COMPLETED", "DONE");

    assertThatThrownBy(() -> jdbc.update(INSERT_GUIDE, VIDEO_ID, JOB_1, 1, "PUBLISHED"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("ck_guides_review_status");
  }

  private List<String> constraints(String table) {
    return jdbc.queryForList(
        "select constraint_name from information_schema.table_constraints where table_name = ?",
        String.class,
        table);
  }

  private List<String> indexes(String table) {
    return jdbc.queryForList(
        "select indexname from pg_indexes where tablename = ?", String.class, table);
  }
}
