package com.mairor.backend.photos.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import io.micrometer.core.instrument.MeterRegistry;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.photos.cleanup-enabled=false"
    })
class PhotoStorageIntegrationTest {
  @Autowired private PhotoUploadService uploads;
  @Autowired private PhotoRecordService records;
  @Autowired private PhotoCleanupService cleanup;
  @Autowired private PhotoTransferService transfers;
  @Autowired private PhotoFileValidator validator;
  @Autowired private PhotoStorageProperties properties;
  @Autowired private PhotoCleanupMetrics metrics;
  @Autowired private MeterRegistry meterRegistry;
  @Autowired private StoredPhotoRepository photos;
  @Autowired private UserRepository users;
  @Autowired private PlatformTransactionManager transactions;
  @MockitoBean private ObjectStorage storage;
  @MockitoBean private Clock clock;
  private UUID userId;
  private final String sessionId = "photo-storage-session";
  private final Instant now = Instant.parse("2026-11-09T00:00:00Z");

  @BeforeEach
  void setUp() {
    photos.deleteAll();
    when(clock.instant()).thenReturn(now);
    userId = users.saveAndFlush(new User(UUID.randomUUID() + "@photo.test", "hash")).getId();
  }

  @Test
  void uploadsRealValidatedMetadataAndClosesTheServerTemporaryFile() throws Exception {
    UUID id = uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image());
    StoredPhoto found = photos.findById(id).orElseThrow();
    assertThat(found.getState()).isEqualTo(PhotoState.AVAILABLE);
    assertThat(found.getContentType()).isEqualTo("image/png");
    assertThat(found.getStorageKey()).startsWith("photos/").doesNotContain(sessionId);
    assertThat(found.getExpiresAt()).isEqualTo(now.plus(properties.stagingTimeout()));
    ArgumentCaptor<Path> path = ArgumentCaptor.forClass(Path.class);
    verify(storage).upload(path.capture(), eq(found.getStorageKey()), eq("image/png"));
    assertThat(path.getValue()).doesNotExist();
  }

  @Test
  void failedUploadRollsBackTransferButDurablyDeletesTheStagedObject() throws Exception {
    doThrow(new StorageException("partial upload", null))
        .when(storage)
        .upload(any(Path.class), anyString(), anyString());
    assertThatThrownBy(
            () -> uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image()))
        .isInstanceOf(StorageException.class);
    StoredPhoto found = onlyPhoto();
    assertThat(found.getState()).isEqualTo(PhotoState.DELETED);
    verify(storage).delete(found.getStorageKey());
  }

  @Test
  void failedCompensationIsRetriedFromTheCommittedDatabaseLedger() throws Exception {
    double failuresBefore = meterRegistry.counter("mairor.photos.cleanup.failures").count();
    doThrow(new StorageException("upload failed", null))
        .when(storage)
        .upload(any(Path.class), anyString(), anyString());
    doThrow(new StorageException("delete failed", null)).when(storage).delete(anyString());
    assertThatThrownBy(
            () -> uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image()))
        .isInstanceOf(StorageException.class);
    StoredPhoto pending = onlyPhoto();
    assertThat(pending.getState()).isEqualTo(PhotoState.CLEANUP_PENDING);
    assertThat(pending.getCleanupAttempts()).isEqualTo(1);
    assertThat(meterRegistry.counter("mairor.photos.cleanup.failures").count())
        .isEqualTo(failuresBefore + 1);
    assertThat(cleanup.cleanup(pending.getId())).isFalse();
    verify(storage, times(1)).delete(anyString());

    when(clock.instant()).thenReturn(now.plus(properties.cleanupRetryDelay()));
    doNothing().when(storage).delete(anyString());
    assertThat(cleanup.cleanup(pending.getId())).isTrue();
    assertThat(cleanup.cleanup(pending.getId())).isTrue();
    assertThat(photos.findById(pending.getId()).orElseThrow().getState())
        .isEqualTo(PhotoState.DELETED);
    verify(storage, times(2)).delete(anyString());
    assertThat(meterRegistry.counter("mairor.photos.cleanup.failures").count())
        .isEqualTo(failuresBefore + 1);
  }

  @Test
  void schedulerReportsOverdueCleanupAndClearsTheGaugeAfterRecovery() throws Exception {
    UUID id = uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image());
    records.requestCleanup(id);
    when(clock.instant()).thenReturn(now.plusSeconds(901));
    doThrow(new StorageException("denied", null)).when(storage).delete(anyString());
    PhotoCleanupScheduler scheduler =
        new PhotoCleanupScheduler(photos, cleanup, properties, clock, metrics);
    scheduler.sweep();
    assertThat(meterRegistry.get("mairor.photos.cleanup.overdue").gauge().value()).isEqualTo(1);
    doNothing().when(storage).delete(anyString());
    when(clock.instant()).thenReturn(now.plusSeconds(1000));
    scheduler.sweep();
    scheduler.sweep();
    assertThat(meterRegistry.get("mairor.photos.cleanup.overdue").gauge().value()).isZero();
  }

  @Test
  void processInterruptionBeforeTransferIsRecoveredAfterStagingTimeout() throws Exception {
    UUID id;
    try (ValidatedPhoto file = validator.validate(image())) {
      id =
          records.stage(
              userId, sessionId, PhotoKind.FACE_REGISTRATION, null, "photos/interrupted", file);
    }
    when(clock.instant()).thenReturn(now.plus(properties.stagingTimeout()));
    new PhotoCleanupScheduler(photos, cleanup, properties, clock, metrics).sweep();
    assertThat(photos.findById(id).orElseThrow().getState()).isEqualTo(PhotoState.DELETED);
    verify(storage).delete("photos/interrupted");
    verify(storage, never()).upload(any(), anyString(), anyString());
  }

  @Test
  void unattachedSuccessfulUploadIsRecoveredIfDomainSaveNeverHappens() throws Exception {
    UUID id = uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image());
    when(clock.instant()).thenReturn(now.plus(properties.stagingTimeout()));
    assertThat(cleanup.cleanup(id)).isTrue();
    assertThat(photos.findById(id).orElseThrow().getState()).isEqualTo(PhotoState.DELETED);
  }

  @Test
  void committedAttachmentStopsOrphanExpiryAndRollbackKeepsTheExpiry() throws Exception {
    UUID attached = uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image());
    UUID rolledBack = uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image());
    TransactionTemplate tx = new TransactionTemplate(transactions);
    tx.executeWithoutResult(status -> records.attach(attached, userId, sessionId));
    tx.executeWithoutResult(
        status -> {
          records.attach(rolledBack, userId, sessionId);
          status.setRollbackOnly();
        });
    when(clock.instant()).thenReturn(now.plus(properties.stagingTimeout()));
    assertThat(cleanup.cleanup(attached)).isFalse();
    assertThat(cleanup.cleanup(rolledBack)).isTrue();
    assertThat(photos.findById(attached).orElseThrow().getExpiresAt()).isNull();
  }

  @Test
  void attachmentRequiresTheOriginalOwnerAndSession() throws Exception {
    UUID id = uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image());
    TransactionTemplate tx = new TransactionTemplate(transactions);
    assertThatThrownBy(() -> tx.execute(status -> records.attach(id, UUID.randomUUID(), sessionId)))
        .isInstanceOf(BusinessException.class);
    assertThatThrownBy(() -> tx.execute(status -> records.attach(id, userId, "other-session")))
        .isInstanceOf(BusinessException.class);
    assertThat(photos.findById(id).orElseThrow().getExpiresAt()).isNotNull();
  }

  @Test
  void expiredUploadIsNeverSentToTheObjectStore() throws Exception {
    try (ValidatedPhoto file = validator.validate(image())) {
      UUID id =
          records.stage(
              userId, sessionId, PhotoKind.FACE_REGISTRATION, null, "photos/expired", file);
      when(clock.instant()).thenReturn(now.plus(properties.stagingTimeout()));
      assertThatThrownBy(() -> transfers.upload(id, file.path()))
          .isInstanceOf(StorageException.class);
      verify(storage, never()).upload(any(), anyString(), anyString());
    }
  }

  @Test
  void cleanupSkipsAnUploadHoldingThePhotoRowLock() throws Exception {
    CountDownLatch entered = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    doAnswer(
            invocation -> {
              entered.countDown();
              if (!release.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("upload test timed out");
              }
              return null;
            })
        .when(storage)
        .upload(any(), anyString(), anyString());
    try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
      Future<UUID> upload =
          executor.submit(
              () -> uploads.store(userId, sessionId, PhotoKind.FACE_REGISTRATION, null, image()));
      try {
        assertThat(entered.await(10, TimeUnit.SECONDS)).isTrue();
        UUID id = onlyPhoto().getId();
        when(clock.instant()).thenReturn(now.plus(properties.stagingTimeout()));
        Future<Boolean> attempt;
        try (ExecutorService cleaner = Executors.newSingleThreadExecutor()) {
          attempt = cleaner.submit(() -> cleanup.cleanup(id));
          assertThat(attempt.get(3, TimeUnit.SECONDS)).isFalse();
        }
        verify(storage, never()).delete(anyString());
      } finally {
        release.countDown();
      }
      UUID id = upload.get(10, TimeUnit.SECONDS);
      assertThat(cleanup.cleanup(id)).isTrue();
    }
  }

  private StoredPhoto onlyPhoto() {
    assertThat(photos.findAll()).hasSize(1);
    return photos.findAll().getFirst();
  }

  private MockMultipartFile image() throws Exception {
    return new MockMultipartFile(
        "image", "face.png", "image/png", PhotoFileValidatorTest.image("png"));
  }
}
