package com.mairor.backend.camera;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.camera.entity.FaceChecks;
import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
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
class FaceRegistrationPersistenceTest {
  @Autowired private FaceRegistrationRepository registrations;
  @Autowired private StoredPhotoRepository photos;
  @Autowired private UserRepository users;
  @Autowired private VideoRepository videos;
  @Autowired private EntityManager em;
  @Autowired private JdbcTemplate jdbc;
  private UUID userId;
  private UUID videoId;
  private final String sessionId = "camera-session";
  private final Instant now = Instant.parse("2026-11-09T00:00:00Z");

  @BeforeEach
  void setUp() {
    userId = users.saveAndFlush(new User("camera@example.com", "hash")).getId();
    videoId =
        videos
            .saveAndFlush(new Video("cameraVideo", "영상", "채널", 60, null, null, "[]", now))
            .getId();
  }

  @Test
  void schemaValidatesAndRegistrationRoundTripsBeforeGuideOrExecutionExists() {
    StoredPhoto photo = savedPhoto();
    FaceRegistration registration = registrations.saveAndFlush(registration(photo));
    em.clear();
    FaceRegistration found =
        registrations
            .findByIdAndUserIdAndSessionIdAndDiscardedAtIsNull(
                registration.getId(), userId, sessionId)
            .orElseThrow();
    assertThat(found.getVideoId()).isEqualTo(videoId);
    assertThat(found.getGuideId()).isNull();
    assertThat(found.getExecutionId()).isNull();
    assertThat(found.getStatus()).isEqualTo(FaceRegistrationStatus.REGISTERED);
    assertThat(found.getPhotoId()).isEqualTo(photo.getId());
    assertThat(found.getChecks().isMakeupDetected()).isTrue();
    assertThat(found.getAgreedAt()).isEqualTo(now);
    assertThat(found.getNoticeVersion()).isEqualTo("v1");
    assertThat(found.getCreatedAt()).isNotNull();
    assertThat(photos.findByIdAndUserId(photo.getId(), userId).orElseThrow().getByteSize())
        .isEqualTo(StoredPhoto.MAX_BYTE_SIZE);
  }

  @Test
  void anotherOwnerOrSessionCannotFindRegistration() {
    FaceRegistration registration = registrations.saveAndFlush(registration(savedPhoto()));
    assertThat(
            registrations.findByIdAndUserIdAndSessionIdAndDiscardedAtIsNull(
                registration.getId(), UUID.randomUUID(), sessionId))
        .isEmpty();
    assertThat(
            registrations.findByIdAndUserIdAndSessionIdAndDiscardedAtIsNull(
                registration.getId(), userId, "other-session"))
        .isEmpty();
  }

  @Test
  void duplicateLiveRegistrationIsRejectedByDatabase() {
    registrations.saveAndFlush(registration(savedPhoto()));
    assertThatThrownBy(() -> registrations.saveAndFlush(registration(savedPhoto())))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(FaceRegistration.ACTIVE_UNIQUE);
  }

  @Test
  void discardedRegistrationReleasesTheRetakeSlotAndIsHidden() {
    FaceRegistration old = registrations.saveAndFlush(registration(savedPhoto()));
    old.discard(now);
    registrations.flush();
    FaceRegistration replacement = registrations.saveAndFlush(registration(savedPhoto()));
    assertThat(replacement.getId()).isNotEqualTo(old.getId());
    assertThat(
            registrations.findByIdAndUserIdAndSessionIdAndDiscardedAtIsNull(
                old.getId(), userId, sessionId))
        .isEmpty();
  }

  @Test
  void databaseRejectsPhotoOwnerMismatchEvenForAnExistingUser() {
    FaceRegistration registration = registrations.saveAndFlush(registration(savedPhoto()));
    UUID other = users.saveAndFlush(new User("other-camera@example.com", "hash")).getId();
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update face_registrations set user_id = ? where id = ?",
                    other,
                    registration.getId()))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("fk_face_registrations_photo_owner");
  }

  @Test
  void databaseRejectsPhotoSessionMismatch() {
    FaceRegistration registration = registrations.saveAndFlush(registration(savedPhoto()));
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update face_registrations set session_id = 'another' where id = ?",
                    registration.getId()))
        .hasMessageContaining("fk_face_registrations_photo_owner");
  }

  @Test
  void databaseRejectsOversizedPhotosWithoutRelyingOnJavaValidation() {
    StoredPhoto photo = savedPhoto();
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update photos set byte_size = ? where id = ?",
                    StoredPhoto.MAX_BYTE_SIZE + 1,
                    photo.getId()))
        .hasMessageContaining("ck_photos_file");
  }

  @Test
  void databaseRequiresAnExecutionForLinkedState() {
    FaceRegistration registration = registrations.saveAndFlush(registration(savedPhoto()));
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update face_registrations set status = 'LINKED' where id = ?",
                    registration.getId()))
        .hasMessageContaining("ck_face_registrations_status");
  }

  @Test
  void databaseRequiresAllMandatoryCaptureChecks() {
    FaceRegistration registration = registrations.saveAndFlush(registration(savedPhoto()));
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update face_registrations set frontal = false where id = ?",
                    registration.getId()))
        .hasMessageContaining("ck_face_registrations_checks");
  }

  @Test
  void cleanupRetryAndDeletionMetadataRoundTripsAndRepeatedRequestsDoNotResetIt() {
    StoredPhoto photo = savedPhoto();
    photo.requestCleanup(now);
    Instant retryAt = now.plusSeconds(60);
    photo.recordCleanupFailure(retryAt);
    photo.requestCleanup(now.plusSeconds(1));
    photos.flush();
    em.clear();
    StoredPhoto pending = photos.findByIdAndUserId(photo.getId(), userId).orElseThrow();
    assertThat(pending.getState()).isEqualTo(PhotoState.CLEANUP_PENDING);
    assertThat(pending.getNextCleanupAt()).isEqualTo(retryAt);
    assertThat(pending.getCleanupAttempts()).isEqualTo(1);
    pending.markDeleted(retryAt);
    pending.markDeleted(retryAt.plusSeconds(1));
    photos.flush();
    em.clear();
    StoredPhoto deleted = photos.findByIdAndUserId(photo.getId(), userId).orElseThrow();
    assertThat(deleted.getState()).isEqualTo(PhotoState.DELETED);
    assertThat(deleted.getDeletedAt()).isEqualTo(retryAt);
    assertThat(deleted.getNextCleanupAt()).isNull();
  }

  @Test
  void productionUpgradeContainsExactlyTheSchemaValidatedHere() throws Exception {
    String schema =
        new ClassPathResource("db/schema/camera.sql").getContentAsString(StandardCharsets.UTF_8);
    String upgrade =
        new ClassPathResource("db/upgrade/396-face-registrations.sql")
            .getContentAsString(StandardCharsets.UTF_8);
    assertThat(
            upgrade.substring(upgrade.indexOf("BEGIN;") + 6, upgrade.lastIndexOf("COMMIT;")).trim())
        .isEqualTo(schema.trim());
  }

  private StoredPhoto savedPhoto() {
    StoredPhoto photo =
        new StoredPhoto(
            userId,
            sessionId,
            PhotoKind.FACE_REGISTRATION,
            null,
            "photos/" + UUID.randomUUID(),
            "image/png",
            StoredPhoto.MAX_BYTE_SIZE,
            640,
            480,
            null);
    photo.markAvailable();
    return photos.saveAndFlush(photo);
  }

  private FaceRegistration registration(StoredPhoto photo) {
    return new FaceRegistration(
        photo, videoId, null, new FaceChecks(true, true, true, true, true), "v1", now);
  }
}
