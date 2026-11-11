package com.mairor.backend.executions;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.camera.entity.FaceChecks;
import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.executions.entity.ExecutionStatus;
import com.mairor.backend.executions.entity.ExecutionStep;
import com.mairor.backend.executions.entity.GuideExecution;
import com.mairor.backend.executions.repository.ExecutionStepRepository;
import com.mairor.backend.executions.repository.GuideExecutionRepository;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import jakarta.persistence.EntityManager;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.io.ClassPathResource;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class ExecutionPersistenceTest {
  private static final Instant NOW = Instant.parse("2026-11-10T00:00:00Z");
  private static final String SESSION = "execution-session";
  @Autowired private GuideExecutionRepository executions;
  @Autowired private ExecutionStepRepository steps;
  @Autowired private FaceRegistrationRepository faces;
  @Autowired private StoredPhotoRepository photos;
  @Autowired private UserRepository users;
  @Autowired private VideoRepository videos;
  @Autowired private EntityManager em;
  @Autowired private JdbcTemplate jdbc;
  private UUID user;
  private UUID video;
  private UUID guide;
  private UUID match;

  @BeforeEach
  void setUp() {
    user = users.saveAndFlush(new User(UUID.randomUUID() + "@execution.test", "hash")).getId();
    video =
        videos.saveAndFlush(new Video("exec-video", "영상", "채널", 60, null, null, "[]", NOW)).getId();
    UUID job = UUID.randomUUID();
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, attempt, created_at, updated_at) values (?, ?, 'COMPLETED', 'DONE', false, 1, now(), now())",
        job,
        video);
    guide = UUID.randomUUID();
    jdbc.update(
        "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input, created_at, updated_at) values (?, ?, ?, 1, 'APPROVED', '{}'::jsonb, now(), now())",
        guide,
        video,
        job);
    match = UUID.randomUUID();
    jdbc.update(
        "insert into guide_matches (id, user_id, guide_id, guide_version, pouch_version, reference_version, compatibility_version, match_snapshot, created_at) values (?, ?, ?, 1, 0, 0, 1, '{}'::jsonb, now())",
        match,
        user,
        guide);
  }

  @Test
  void schemaValidatesAndSnapshotsSurviveChangesToTheSourceGuide() {
    GuideExecution execution = savedExecution();
    steps.saveAndFlush(
        new ExecutionStep(
            execution,
            "lip",
            1,
            false,
            "{\"selectedProduct\":{\"name\":\"원래 제품\"},\"selectedColor\":{\"hex\":\"#AABBCC\"}}"));
    steps.saveAndFlush(new ExecutionStep(execution, "eye", 0, true, "{\"result\":\"NONE\"}"));
    jdbc.update(
        "update guides set guide_input = '{\"changed\":true}'::jsonb, reference_version = 1 where id = ?",
        guide);
    em.clear();
    GuideExecution found = executions.findByIdAndUserId(execution.getId(), user).orElseThrow();
    assertThat(found.getGuideSnapshot()).contains("원래 영상");
    assertThat(found.getReferenceVersion()).isZero();
    assertThat(found.getPhotoConsent()).isNull();
    assertThat(found.getRecordId()).isNull();
    assertThat(found.getCreatedAt()).isNotNull();
    assertThat(steps.findByExecutionIdOrderByPosition(found.getId()))
        .extracting(ExecutionStep::getStepId)
        .containsExactly("eye", "lip");
    assertThat(
            steps.findByExecutionIdAndStepId(found.getId(), "lip").orElseThrow().getStepSnapshot())
        .contains("원래 제품", "#AABBCC");
    assertThat(executions.findByIdAndUserId(found.getId(), UUID.randomUUID())).isEmpty();
    assertThat(
            executions.findByUserIdAndSessionIdAndStatusOrderById(
                user, "other-session", ExecutionStatus.IN_PROGRESS))
        .isEmpty();
  }

  @Test
  void executionAndFaceLinkRoundTripInOneTransaction() {
    GuideExecution execution = savedExecution();
    FaceRegistration face = faces.findById(execution.getFaceRegistrationId()).orElseThrow();
    face.linkToExecution(guide, execution.getId());
    faces.flush();
    em.clear();
    assertThat(faces.findById(face.getId()).orElseThrow().getExecutionId())
        .isEqualTo(execution.getId());
    assertThat(executions.findOwnedForUpdate(execution.getId(), user)).isPresent();
  }

  @Test
  void faceCannotPointToANonexistentExecution() {
    FaceRegistration face = faces.findById(savedExecution().getFaceRegistrationId()).orElseThrow();
    face.linkToExecution(guide, UUID.randomUUID());
    assertThatThrownBy(() -> faces.flush())
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("fk_face_registrations_execution_owner");
  }

  @Test
  void anotherSessionsFaceCannotBeAttachedToAnExecution() {
    FaceRegistration face = savedFace("other-session");
    assertThatThrownBy(() -> executions.saveAndFlush(execution(face.getId())))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("fk_guide_executions_face_owner");
  }

  @Test
  void foreignMatchCannotBeUsedEvenIfTheGuideIsTheSame() {
    UUID other = users.saveAndFlush(new User("other@execution.test", "hash")).getId();
    jdbc.update("update guide_matches set user_id = ? where id = ?", other, match);
    assertThatThrownBy(this::savedExecution)
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("fk_guide_executions_match_owner_guide");
  }

  @Test
  void sameFaceCannotBeReusedByAnotherExecution() {
    GuideExecution execution = savedExecution();
    assertThatThrownBy(() -> executions.saveAndFlush(execution(execution.getFaceRegistrationId())))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("uk_guide_executions_face");
  }

  @Test
  void duplicateStepIsRejected() {
    GuideExecution execution = savedExecution();
    steps.saveAndFlush(new ExecutionStep(execution, "lip", 0, false, "{}"));
    assertThatThrownBy(
            () -> steps.saveAndFlush(new ExecutionStep(execution, "lip", 1, false, "{}")))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("uk_execution_steps_step");
  }

  @Test
  void stepCannotClaimADifferentOwner() {
    ExecutionStep step =
        steps.saveAndFlush(new ExecutionStep(savedExecution(), "lip", 0, false, "{}"));
    UUID other = users.saveAndFlush(new User("step-other@execution.test", "hash")).getId();
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update execution_steps set user_id = ? where id = ?", other, step.getId()))
        .hasMessageContaining("fk_execution_steps_execution_owner");
  }

  @Test
  void databaseRejectsAPhotoFromAnotherStep() {
    ExecutionStep step =
        steps.saveAndFlush(new ExecutionStep(savedExecution(), "lip", 0, false, "{}"));
    StoredPhoto photo = savedPhoto(SESSION, PhotoKind.STEP, "eye");
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update execution_steps set photo_id = ? where id = ?",
                    photo.getId(),
                    step.getId()))
        .hasMessageContaining("fk_execution_steps_photo_owner_step");
  }

  @Test
  void stepPhotoCanBeAttachedButSkippedStepsAndStagingPhotosAreRejected() {
    GuideExecution execution = savedExecution();
    ExecutionStep step = steps.saveAndFlush(new ExecutionStep(execution, "lip", 0, false, "{}"));
    StoredPhoto photo = savedPhoto(SESSION, PhotoKind.STEP, "lip");
    step.attachPhoto(photo);
    steps.flush();
    em.clear();
    assertThat(
            steps.findByExecutionIdAndStepId(execution.getId(), "lip").orElseThrow().getPhotoId())
        .isEqualTo(photo.getId());
    ExecutionStep skipped = new ExecutionStep(execution, "lip", 1, true, "{}");
    assertThatThrownBy(() -> skipped.attachPhoto(photo))
        .isInstanceOf(IllegalArgumentException.class);
    StoredPhoto staging =
        new StoredPhoto(
            user,
            SESSION,
            PhotoKind.STEP,
            "lip",
            "photos/" + UUID.randomUUID(),
            "image/png",
            10,
            2,
            2,
            NOW.plusSeconds(60));
    staging.markAvailable();
    photos.saveAndFlush(staging);
    assertThatThrownBy(() -> step.attachPhoto(staging))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void completionKeepsTheOriginalRecordAndTimestampAndRejectsAbandonment() {
    GuideExecution execution = savedExecution();
    UUID record = UUID.randomUUID();
    execution.complete(record, NOW);
    execution.complete(record, NOW.plusSeconds(60));
    executions.flush();
    em.clear();
    GuideExecution found = executions.findById(execution.getId()).orElseThrow();
    assertThat(found.getStatus()).isEqualTo(ExecutionStatus.COMPLETED);
    assertThat(found.getRecordId()).isEqualTo(record);
    assertThat(found.getCompletedAt()).isEqualTo(NOW);
    assertThatThrownBy(() -> found.complete(UUID.randomUUID(), NOW))
        .isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> found.abandon(NOW)).isInstanceOf(IllegalStateException.class);
  }

  @Test
  void abandonmentIsIdempotentAndCannotBeCompleted() {
    GuideExecution execution = savedExecution();
    execution.abandon(NOW);
    execution.abandon(NOW.plusSeconds(60));
    executions.flush();
    em.clear();
    GuideExecution found = executions.findById(execution.getId()).orElseThrow();
    assertThat(found.getAbandonedAt()).isEqualTo(NOW);
    assertThat(found.getRecordId()).isNull();
    assertThatThrownBy(() -> found.complete(UUID.randomUUID(), NOW))
        .isInstanceOf(IllegalStateException.class);
  }

  @Test
  void databaseRejectsCompletedStateWithoutARecord() {
    GuideExecution execution = savedExecution();
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update guide_executions set status = 'COMPLETED', completed_at = now() where id = ?",
                    execution.getId()))
        .hasMessageContaining("ck_guide_executions_status");
  }

  @Test
  void databaseRejectsConsentWithoutItsPolicyAndTimestamp() {
    GuideExecution execution = savedExecution();
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update guide_executions set photo_consent = true where id = ?",
                    execution.getId()))
        .hasMessageContaining("ck_guide_executions_consent");
  }

  @Test
  void recordIdCannotBeSharedByTwoExecutions() {
    GuideExecution first = savedExecution();
    faces
        .findById(first.getFaceRegistrationId())
        .orElseThrow()
        .linkToExecution(guide, first.getId());
    faces.flush();
    UUID record = UUID.randomUUID();
    first.complete(record, NOW);
    executions.flush();
    GuideExecution second = savedExecution();
    second.complete(record, NOW);
    assertThatThrownBy(() -> executions.flush())
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("uk_guide_executions_record");
  }

  @Test
  void databaseRejectsArraySnapshots() {
    assertThatThrownBy(
            () -> steps.saveAndFlush(new ExecutionStep(savedExecution(), "lip", 0, false, "[]")))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("ck_execution_steps_snapshot");
  }

  @Test
  void productionUpgradeContainsTheSameSchema() throws Exception {
    String schema =
        new ClassPathResource("db/schema/executions.sql")
            .getContentAsString(StandardCharsets.UTF_8);
    String upgrade =
        new ClassPathResource("db/upgrade/395-guide-executions.sql")
            .getContentAsString(StandardCharsets.UTF_8);
    assertThat(
            upgrade.substring(upgrade.indexOf("BEGIN;") + 6, upgrade.lastIndexOf("COMMIT;")).trim())
        .isEqualTo(schema.trim());
  }

  private GuideExecution savedExecution() {
    return executions.saveAndFlush(execution(savedFace(SESSION).getId()));
  }

  private GuideExecution execution(UUID face) {
    return new GuideExecution(
        UUID.randomUUID(), user, SESSION, guide, match, face, 1, 0, 0, 1, "{\"title\":\"원래 영상\"}");
  }

  private FaceRegistration savedFace(String session) {
    return faces.saveAndFlush(
        new FaceRegistration(
            savedPhoto(session, PhotoKind.FACE_REGISTRATION, null),
            video,
            guide,
            new FaceChecks(true, true, true, true, false),
            "v1",
            NOW));
  }

  private StoredPhoto savedPhoto(String session, PhotoKind kind, String step) {
    StoredPhoto photo =
        new StoredPhoto(
            user, session, kind, step, "photos/" + UUID.randomUUID(), "image/png", 10, 2, 2, null);
    photo.markAvailable();
    return photos.saveAndFlush(photo);
  }
}
