package com.mairor.backend.camera;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doCallRealMethod;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.camera.dto.FaceChecksData;
import com.mairor.backend.camera.dto.FaceRegistrationRequest;
import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import com.mairor.backend.camera.repository.FaceRegistrationOrphanRepository;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.camera.service.FaceRegistrationExecutionService;
import com.mairor.backend.camera.service.FaceRegistrationLifecycleService;
import com.mairor.backend.camera.service.FaceRegistrationOrphanScheduler;
import com.mairor.backend.camera.service.FaceRegistrationProperties;
import com.mairor.backend.camera.service.FaceRegistrationService;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.security.ExpiredSessionSweeper;
import com.mairor.backend.common.security.SessionAttributes;
import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndNotifier;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.photos.service.PhotoRecordService;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.AuthenticatedUser;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import jakarta.servlet.http.Cookie;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextImpl;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.SessionRepositoryFilter;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.util.AopTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockMultipartHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.context.WebApplicationContext;

@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.photos.cleanup-enabled=false",
      "app.face-registration.orphan-cleanup-enabled=false"
    })
@AutoConfigureMockMvc
class FaceRegistrationApiTest {
  private static final String PATH = "/v1/users/me/face-registrations";
  private MockMvc mvc;
  @Autowired private WebApplicationContext context;
  @Autowired private SessionRepositoryFilter<?> sessionFilter;
  @Autowired private CookieSerializer cookieSerializer;
  @Autowired private UserRepository users;
  @Autowired private VideoRepository videos;
  @Autowired private StoredPhotoRepository photos;
  @MockitoSpyBean private FaceRegistrationRepository registrations;
  @Autowired private FaceRegistrationService service;
  @Autowired private FaceRegistrationExecutionService executions;
  @Autowired private FaceRegistrationLifecycleService lifecycle;
  @Autowired private FaceRegistrationOrphanRepository orphans;
  @Autowired private FaceRegistrationProperties registrationProperties;
  @Autowired private SessionEndNotifier sessionEnd;
  @Autowired private ExpiredSessionSweeper sessionSweeper;
  @Autowired private PlatformTransactionManager transactions;
  @MockitoSpyBean private PhotoRecordService photoRecords;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private FindByIndexNameSessionRepository<? extends Session> sessions;
  @MockitoBean private ObjectStorage storage;
  private UUID userId;
  private UUID videoId;
  private Login login;

  @BeforeEach
  void setUp() {
    // 원래 세션 인가를 검증하므로 JDBC 세션 복원이 SecurityContext 조회보다 먼저 실행돼야 한다.
    mvc =
        MockMvcBuilders.webAppContextSetup(context)
            .addFilters(sessionFilter)
            .apply(springSecurity())
            .build();
    registrations.deleteAll();
    photos.deleteAll();
    userId = users.saveAndFlush(new User(UUID.randomUUID() + "@camera.test", "hash")).getId();
    videoId = video();
    login = login(sessions, userId);
  }

  @Test
  void multipartRegistrationAndGetReturnTheContractWithoutInternalMetadata() throws Exception {
    String body = register(login, metadata()).getResponse().getContentAsString();
    UUID id = id(body);
    mvc.perform(get(PATH + "/" + id).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.videoId").value(videoId.toString()))
        .andExpect(jsonPath("$.guideId").isEmpty())
        .andExpect(jsonPath("$.executionId").isEmpty())
        .andExpect(jsonPath("$.status").value("REGISTERED"))
        .andExpect(jsonPath("$.checks.makeupDetected").value(true))
        .andExpect(jsonPath("$.noticeVersion").value("v1"))
        .andExpect(jsonPath("$.agreedAt").isNotEmpty())
        .andExpect(jsonPath("$.photo.kind").value("FACE_REGISTRATION"))
        .andExpect(jsonPath("$.photo.contentType").value("image/png"))
        .andExpect(jsonPath("$.photo.width").value(3))
        .andExpect(jsonPath("$.photo.height").value(2));
    assertThat(body).doesNotContain("storageKey", "sessionId", login.id());
    assertThat(JsonPath.<String>read(body, "$.photo.url")).startsWith("/api/v1/users/me/photos/");
    assertThat(photos.findAll().getFirst().getExpiresAt()).isNull();
  }

  @Test
  void retakeDiscardsOnlyThePreviousUnlinkedRegistrationAfterSuccess() throws Exception {
    UUID first = id(register(login, metadata()).getResponse().getContentAsString());
    UUID second = id(register(login, metadata()).getResponse().getContentAsString());
    mvc.perform(get(PATH + "/" + first).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
    mvc.perform(get(PATH + "/" + second).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk());
    assertThat(registrations.findById(first).orElseThrow().getDiscardedAt()).isNotNull();
    assertThat(photos.findAll())
        .extracting(photo -> photo.getState())
        .containsExactlyInAnyOrder(PhotoState.DELETED, PhotoState.AVAILABLE);
  }

  @Test
  void anotherSessionGetsItsOwnRegistrationWithoutDiscardingTheFirst() throws Exception {
    UUID first = id(register(login, metadata()).getResponse().getContentAsString());
    Login another = login(sessions, userId);
    register(another, metadata());
    mvc.perform(get(PATH + "/" + first).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk());
    assertThat(registrations.findAll())
        .allSatisfy(value -> assertThat(value.getDiscardedAt()).isNull());
  }

  @Test
  void requiredConditionsConsentAndNoticeErrorsAreDocumentedCodes() throws Exception {
    expectError(
        metadata().replace("\"agreed\":true", "\"agreed\":false"), 400, "FACE_CONSENT_REQUIRED");
    expectError(
        metadata().replace("\"noticeVersion\":\"v1\"", "\"noticeVersion\":\"old\""),
        400,
        "FACE_NOTICE_VERSION_INVALID");
    for (String condition : List.of("lighting", "distance", "frontal", "unobstructed")) {
      expectError(
          metadata().replace("\"" + condition + "\":true", "\"" + condition + "\":false"),
          400,
          "FACE_CONDITIONS_NOT_MET");
    }
    assertThat(photos.count()).isZero();
    verify(storage, never()).upload(any(Path.class), anyString(), anyString());
  }

  @Test
  void nonexistentVideoAndMismatchedGuideAre404BeforeUploading() throws Exception {
    expectError(
        metadata().replace(videoId.toString(), UUID.randomUUID().toString()), 404, "NOT_FOUND");
    UUID guide = guide(video(), "APPROVED");
    expectError(
        metadata().replace("\"guideId\":null", "\"guideId\":\"" + guide + "\""), 404, "NOT_FOUND");
    assertThat(photos.count()).isZero();
  }

  @Test
  void sameVideoApprovedGuideCanBeRecorded() throws Exception {
    UUID guide = guide(videoId, "APPROVED");
    String body =
        register(login, metadata().replace("\"guideId\":null", "\"guideId\":\"" + guide + "\""))
            .getResponse()
            .getContentAsString();
    assertThat(JsonPath.<String>read(body, "$.guideId")).isEqualTo(guide.toString());
  }

  @Test
  void unapprovedGuideCannotBeRecorded() throws Exception {
    UUID guide = guide(videoId, "PENDING");
    expectError(
        metadata().replace("\"guideId\":null", "\"guideId\":\"" + guide + "\""), 404, "NOT_FOUND");
  }

  @Test
  void invalidJsonUuidMissingMetadataAndMissingImageAre400() throws Exception {
    expectError(metadata().replace(videoId.toString(), "not-a-uuid"), 400, "VALIDATION_FAILED");
    mvc.perform(multipart(PATH).file(image()).cookie(login.cookie()).secure(true).with(csrf()))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    mvc.perform(
            multipart(PATH).file(json(metadata())).cookie(login.cookie()).secure(true).with(csrf()))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void actualImageFormatAndSizeAreEnforcedAtTheApi() throws Exception {
    mvc.perform(
            write(login, metadata())
                .file(
                    new MockMultipartFile("image", "fake.png", "image/png", new byte[] {1, 2, 3})))
        .andExpect(status().isUnsupportedMediaType())
        .andExpect(jsonPath("$.code").value("UNSUPPORTED_MEDIA_TYPE"));
    mvc.perform(
            write(login, metadata())
                .file(new MockMultipartFile("image", new byte[5 * 1024 * 1024 + 1])))
        .andExpect(status().isPayloadTooLarge())
        .andExpect(jsonPath("$.code").value("PAYLOAD_TOO_LARGE"));
    assertThat(photos.count()).isZero();
  }

  @Test
  void anotherOwnerAndAnotherSessionBothReceive404ForReadAndDelete() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    UUID otherUser =
        users.saveAndFlush(new User(UUID.randomUUID() + "@camera.test", "hash")).getId();
    for (Login denied : List.of(login(sessions, otherUser), login(sessions, userId))) {
      mvc.perform(get(PATH + "/" + id).cookie(denied.cookie()).secure(true))
          .andExpect(status().isNotFound())
          .andExpect(jsonPath("$.code").value("NOT_FOUND"));
      mvc.perform(delete(PATH + "/" + id).cookie(denied.cookie()).secure(true).with(csrf()))
          .andExpect(status().isNotFound())
          .andExpect(jsonPath("$.code").value("NOT_FOUND"));
    }
  }

  @Test
  void deleteWaitsForFileDeletionAndRepeatedDeleteIs404() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    mvc.perform(delete(PATH + "/" + id).cookie(login.cookie()).secure(true).with(csrf()))
        .andExpect(status().isNoContent());
    mvc.perform(get(PATH + "/" + id).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
    mvc.perform(delete(PATH + "/" + id).cookie(login.cookie()).secure(true).with(csrf()))
        .andExpect(status().isNotFound());
    assertThat(photos.findAll().getFirst().getState()).isEqualTo(PhotoState.DELETED);
  }

  @Test
  void deletionFailureBlocksReadsAndTheSameDeleteCanFinishLater() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    doThrow(new StorageException("unavailable", null)).when(storage).delete(anyString());
    mvc.perform(delete(PATH + "/" + id).cookie(login.cookie()).secure(true).with(csrf()))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("SERVICE_UNAVAILABLE"));
    mvc.perform(get(PATH + "/" + id).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
    assertThat(photos.findAll().getFirst().getState()).isEqualTo(PhotoState.CLEANUP_PENDING);
    jdbc.update("update photos set next_cleanup_at = now() - interval '1 second'");
    doNothing().when(storage).delete(anyString());
    mvc.perform(delete(PATH + "/" + id).cookie(login.cookie()).secure(true).with(csrf()))
        .andExpect(status().isNoContent());
  }

  @Test
  void linkedAndRetainedRegistrationsCannotBeDeletedDirectly() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    for (String state : List.of("LINKED", "RETAINED")) {
      jdbc.update(
          "update face_registrations set status = ?, execution_id = ? where id = ?",
          state,
          UUID.randomUUID(),
          id);
      mvc.perform(delete(PATH + "/" + id).cookie(login.cookie()).secure(true).with(csrf()))
          .andExpect(status().isConflict())
          .andExpect(jsonPath("$.code").value("FACE_REGISTRATION_IN_USE"));
    }
    Login otherSession = login(sessions, userId);
    mvc.perform(get(PATH + "/" + id).cookie(otherSession.cookie()).secure(true))
        .andExpect(status().isOk());
  }

  @Test
  void uploadFailureDoesNotDiscardTheExistingRegistration() throws Exception {
    UUID first = id(register(login, metadata()).getResponse().getContentAsString());
    doThrow(new StorageException("partial upload", null))
        .when(storage)
        .upload(any(Path.class), anyString(), anyString());
    expectError(metadata(), 503, "SERVICE_UNAVAILABLE");
    mvc.perform(get(PATH + "/" + first).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk());
    assertThat(registrations.count()).isEqualTo(1);
  }

  @Test
  void databaseFailureAfterDiscardFlushRestoresTheOldRegistrationAndCleansTheNewPhoto()
      throws Exception {
    UUID first = id(register(login, metadata()).getResponse().getContentAsString());
    doThrow(new DataIntegrityViolationException("simulated save failure"))
        .when(registrations)
        .saveAndFlush(any(FaceRegistration.class));
    assertThatThrownBy(
            () ->
                service.register(
                    userId,
                    login.id(),
                    new FaceRegistrationRequest(
                        videoId,
                        null,
                        "v1",
                        true,
                        new FaceChecksData(true, true, true, true, false)),
                    image()))
        .isInstanceOf(DataIntegrityViolationException.class);
    mvc.perform(get(PATH + "/" + first).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk());
    assertThat(photos.findAll())
        .extracting(photo -> photo.getState())
        .containsExactlyInAnyOrder(PhotoState.AVAILABLE, PhotoState.DELETED);
  }

  @Test
  void previousFileCleanupFailureDoesNotFailTheSuccessfulRetake() throws Exception {
    UUID first = id(register(login, metadata()).getResponse().getContentAsString());
    doThrow(new StorageException("delete failed", null)).when(storage).delete(anyString());
    UUID second = id(register(login, metadata()).getResponse().getContentAsString());
    mvc.perform(get(PATH + "/" + first).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
    mvc.perform(get(PATH + "/" + second).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk());
  }

  @Test
  void concurrentRetakesSerializeToOneActiveRegistration() throws Exception {
    FaceRegistrationRequest request =
        new FaceRegistrationRequest(
            videoId, null, "v1", true, new FaceChecksData(true, true, true, true, false));
    try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
      Future<?> one =
          executor.submit(() -> service.register(userId, login.id(), request, uncheckedImage()));
      Future<?> two =
          executor.submit(() -> service.register(userId, login.id(), request, uncheckedImage()));
      one.get(10, TimeUnit.SECONDS);
      two.get(10, TimeUnit.SECONDS);
    }
    assertThat(
            registrations.findAll().stream()
                .filter(value -> value.getDiscardedAt() == null)
                .count())
        .isEqualTo(1);
    assertThat(photos.findAll())
        .extracting(photo -> photo.getState())
        .containsExactlyInAnyOrder(PhotoState.DELETED, PhotoState.AVAILABLE);
  }

  @Test
  void authenticationAndCsrfAreRequired() throws Exception {
    mvc.perform(get(PATH + "/" + UUID.randomUUID())).andExpect(status().isUnauthorized());
    mvc.perform(multipart(PATH).file(json(metadata())).file(image()).secure(true).with(csrf()))
        .andExpect(status().isUnauthorized());
    mvc.perform(
            multipart(PATH)
                .file(json(metadata()))
                .file(image())
                .cookie(login.cookie())
                .secure(true))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
  }

  @ParameterizedTest
  @EnumSource(SessionEndReason.class)
  void everySessionEndReasonOnlyDiscardsUnlinkedRegistrationsOfThatSession(SessionEndReason reason)
      throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    Login another = login(sessions, userId);
    UUID untouched = id(register(another, metadata()).getResponse().getContentAsString());
    SessionEnd end = new SessionEnd(userId.toString(), login.id(), reason);
    sessionEnd.strict(end);
    var first =
        photos.findById(registrations.findById(id).orElseThrow().getPhotoId()).orElseThrow();
    var requestedAt = first.getCleanupRequestedAt();
    sessionEnd.strict(end);
    assertThat(registrations.findById(id).orElseThrow().getDiscardedAt()).isNotNull();
    assertThat(registrations.findById(untouched).orElseThrow().getDiscardedAt()).isNull();
    var repeated = photos.findById(first.getId()).orElseThrow();
    assertThat(repeated.getState()).isEqualTo(PhotoState.CLEANUP_PENDING);
    assertThat(repeated.getCleanupRequestedAt()).isEqualTo(requestedAt);
    verify(storage, never()).delete(anyString());
  }

  @Test
  void actualLogoutCallsTheFaceRegistrationHookBeforeDeletingTheSession() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    mvc.perform(post("/v1/users/logout").cookie(login.cookie()).secure(true).with(csrf()))
        .andExpect(status().isNoContent());
    assertThat(sessions.findById(login.id())).isNull();
    assertThat(registrations.findById(id).orElseThrow().getDiscardedAt()).isNotNull();
    assertThat(photos.findAll().getFirst().getState()).isEqualTo(PhotoState.CLEANUP_PENDING);
    verify(storage, never()).delete(anyString());
  }

  @Test
  void idleSessionSweepCallsTheHookAndBlocksRegistrationAccess() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    jdbc.update(
        "update spring_session set expiry_time = ? where session_id = ?",
        System.currentTimeMillis() - 1,
        login.id());
    sessionSweeper.sweep();
    assertThat(registrations.findById(id).orElseThrow().getDiscardedAt()).isNotNull();
    assertThat(sessions.findById(login.id())).isNull();
  }

  @Test
  void missingSessionReconciliationRecoversAMissedHookAndPreservesExistingSessions()
      throws Exception {
    UUID missing = id(register(login, metadata()).getResponse().getContentAsString());
    Login valid = login(sessions, userId);
    UUID alive = id(register(valid, metadata()).getResponse().getContentAsString());
    sessions.deleteById(login.id());
    new FaceRegistrationOrphanScheduler(orphans, lifecycle, registrationProperties).sweep();
    assertThat(registrations.findById(missing).orElseThrow().getDiscardedAt()).isNotNull();
    assertThat(registrations.findById(alive).orElseThrow().getDiscardedAt()).isNull();
  }

  @Test
  void liveSessionRegistrationHasNoFixedHourOrDayExpiry() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    jdbc.update(
        "update face_registrations set created_at = now() - interval '7 days' where id = ?", id);
    new FaceRegistrationOrphanScheduler(orphans, lifecycle, registrationProperties).sweep();
    mvc.perform(get(PATH + "/" + id).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk());
    assertThat(photos.findAll().getFirst().getExpiresAt()).isNull();
  }

  @Test
  void failedSessionHookRollsBackBothDiscardAndCleanupAndCanBeRetried() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    PhotoRecordService recordTarget = AopTestUtils.getUltimateTargetObject(photoRecords);
    doThrow(new IllegalStateException("simulated cleanup DB failure"))
        .when(recordTarget)
        .requestCleanupInCurrentTransaction(any(UUID.class));
    SessionEnd end = new SessionEnd(userId.toString(), login.id(), SessionEndReason.LOGOUT);
    assertThatThrownBy(() -> sessionEnd.strict(end)).isInstanceOf(IllegalStateException.class);
    assertThat(registrations.findById(id).orElseThrow().getDiscardedAt()).isNull();
    assertThat(photos.findAll().getFirst().getState()).isEqualTo(PhotoState.AVAILABLE);
    doCallRealMethod().when(recordTarget).requestCleanupInCurrentTransaction(any(UUID.class));
    sessionEnd.strict(end);
    assertThat(registrations.findById(id).orElseThrow().getDiscardedAt()).isNotNull();
  }

  @Test
  void executionLinkRequiresTheCallersTransactionAndRollsBackWithIt() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    UUID guide = guide(videoId, "APPROVED");
    UUID execution = UUID.randomUUID();
    assertThatThrownBy(() -> executions.link(userId, login.id(), id, videoId, guide, execution))
        .isInstanceOf(IllegalTransactionStateException.class);
    new TransactionTemplate(transactions)
        .executeWithoutResult(
            status -> {
              executions.link(userId, login.id(), id, videoId, guide, execution);
              status.setRollbackOnly();
            });
    FaceRegistration found = registrations.findById(id).orElseThrow();
    assertThat(found.getStatus()).isEqualTo(FaceRegistrationStatus.REGISTERED);
    assertThat(found.getExecutionId()).isNull();
  }

  @Test
  void executionLinkRejectsWrongOwnerSessionVideoGuideAndReusedRegistration() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    UUID guide = guide(videoId, "APPROVED");
    UUID execution = UUID.randomUUID();
    UUID otherUser =
        users.saveAndFlush(new User(UUID.randomUUID() + "@camera.test", "hash")).getId();
    assertBusiness(
        () -> tx(() -> executions.link(otherUser, login.id(), id, videoId, guide, execution)),
        "NOT_FOUND");
    assertBusiness(
        () -> tx(() -> executions.link(userId, "wrong-session", id, videoId, guide, execution)),
        "NOT_FOUND");
    assertBusiness(
        () -> tx(() -> executions.link(userId, login.id(), id, video(), guide, execution)),
        "NOT_FOUND");
    assertBusiness(
        () ->
            tx(
                () ->
                    executions.link(userId, login.id(), id, videoId, UUID.randomUUID(), execution)),
        "NOT_FOUND");
    tx(() -> executions.link(userId, login.id(), id, videoId, guide, execution));
    assertThat(registrations.findById(id).orElseThrow().getGuideId()).isEqualTo(guide);
    assertBusiness(
        () -> tx(() -> executions.link(userId, login.id(), id, videoId, guide, execution)),
        "FACE_REGISTRATION_ALREADY_USED");
  }

  @Test
  void concurrentExecutionLinksCannotReuseTheSameFaceRegistration() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    UUID guide = guide(videoId, "APPROVED");
    java.util.concurrent.Callable<String> link =
        () -> {
          try {
            tx(() -> executions.link(userId, login.id(), id, videoId, guide, UUID.randomUUID()));
            return "LINKED";
          } catch (BusinessException e) {
            return e.code();
          }
        };
    try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
      Future<String> one = executor.submit(link);
      Future<String> two = executor.submit(link);
      assertThat(List.of(one.get(10, TimeUnit.SECONDS), two.get(10, TimeUnit.SECONDS)))
          .containsExactlyInAnyOrder("LINKED", "FACE_REGISTRATION_ALREADY_USED");
    }
  }

  @Test
  void retainIsAtomicAndIdempotentAndProtectsTheCompletedPhotoFromAbandonment() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    UUID execution = UUID.randomUUID();
    UUID guide = guide(videoId, "APPROVED");
    tx(() -> executions.link(userId, login.id(), id, videoId, guide, execution));
    new TransactionTemplate(transactions)
        .executeWithoutResult(
            status -> {
              executions.retain(userId, login.id(), id, execution);
              status.setRollbackOnly();
            });
    assertThat(registrations.findById(id).orElseThrow().getStatus())
        .isEqualTo(FaceRegistrationStatus.LINKED);
    tx(() -> executions.retain(userId, login.id(), id, execution));
    tx(() -> executions.retain(userId, login.id(), id, execution));
    assertBusiness(
        () -> tx(() -> executions.abandon(userId, login.id(), id, execution)),
        "FACE_REGISTRATION_IN_USE");
    assertThat(registrations.findById(id).orElseThrow().getStatus())
        .isEqualTo(FaceRegistrationStatus.RETAINED);
    assertThat(photos.findAll().getFirst().getState()).isEqualTo(PhotoState.AVAILABLE);
  }

  @Test
  void linkedAndRetainedPhotosSurviveTheUnlinkedSessionCleanup() throws Exception {
    UUID linked = id(register(login, metadata()).getResponse().getContentAsString());
    UUID guide = guide(videoId, "APPROVED");
    tx(() -> executions.link(userId, login.id(), linked, videoId, guide, UUID.randomUUID()));
    UUID retained = id(register(login, metadata()).getResponse().getContentAsString());
    UUID retainedExecution = UUID.randomUUID();
    tx(() -> executions.link(userId, login.id(), retained, videoId, guide, retainedExecution));
    tx(() -> executions.retain(userId, login.id(), retained, retainedExecution));
    UUID unlinked = id(register(login, metadata()).getResponse().getContentAsString());
    sessionEnd.strict(new SessionEnd(userId.toString(), login.id(), SessionEndReason.LOGOUT));
    assertThat(registrations.findById(linked).orElseThrow().getDiscardedAt()).isNull();
    assertThat(registrations.findById(retained).orElseThrow().getDiscardedAt()).isNull();
    assertThat(registrations.findById(unlinked).orElseThrow().getDiscardedAt()).isNotNull();
  }

  @Test
  void abandonmentIsIdempotentAndValidatesTheExecutionAssociation() throws Exception {
    UUID id = id(register(login, metadata()).getResponse().getContentAsString());
    UUID execution = UUID.randomUUID();
    UUID guide = guide(videoId, "APPROVED");
    tx(() -> executions.link(userId, login.id(), id, videoId, guide, execution));
    assertBusiness(
        () -> tx(() -> executions.abandon(userId, login.id(), id, UUID.randomUUID())), "NOT_FOUND");
    tx(() -> executions.abandon(userId, login.id(), id, execution));
    var discardedAt = registrations.findById(id).orElseThrow().getDiscardedAt();
    tx(() -> executions.abandon(userId, login.id(), id, execution));
    assertThat(registrations.findById(id).orElseThrow().getDiscardedAt()).isEqualTo(discardedAt);
    assertThat(photos.findAll().getFirst().getState()).isEqualTo(PhotoState.CLEANUP_PENDING);
    mvc.perform(get(PATH + "/" + id).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
  }

  private void tx(Runnable call) {
    new TransactionTemplate(transactions).executeWithoutResult(status -> call.run());
  }

  private void assertBusiness(
      org.assertj.core.api.ThrowableAssert.ThrowingCallable call, String code) {
    assertThatThrownBy(call)
        .isInstanceOfSatisfying(
            BusinessException.class, exception -> assertThat(exception.code()).isEqualTo(code));
  }

  private org.springframework.test.web.servlet.MvcResult register(Login session, String metadata)
      throws Exception {
    return mvc.perform(write(session, metadata).file(image()))
        .andExpect(status().isCreated())
        .andReturn();
  }

  private MockMultipartHttpServletRequestBuilder write(Login session, String metadata) {
    MockMultipartHttpServletRequestBuilder request = multipart(PATH).file(json(metadata));
    request.cookie(session.cookie()).secure(true).with(csrf());
    return request;
  }

  private MockMultipartFile json(String json) {
    return new MockMultipartFile(
        "metadata", "", "application/json", json.getBytes(StandardCharsets.UTF_8));
  }

  private void expectError(String metadata, int statusCode, String code) throws Exception {
    mvc.perform(write(login, metadata).file(image()))
        .andExpect(status().is(statusCode))
        .andExpect(jsonPath("$.code").value(code));
  }

  private String metadata() {
    return """
        {"videoId":"%s","guideId":null,"noticeVersion":"v1","agreed":true,
        "checks":{"lighting":true,"distance":true,"frontal":true,"unobstructed":true,"makeupDetected":true}}
        """
        .formatted(videoId);
  }

  private UUID id(String response) {
    return UUID.fromString(JsonPath.read(response, "$.faceRegistrationId"));
  }

  private MockMultipartFile image() throws Exception {
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    ImageIO.write(new BufferedImage(3, 2, BufferedImage.TYPE_INT_RGB), "png", bytes);
    return new MockMultipartFile("image", "face.png", "image/png", bytes.toByteArray());
  }

  private MockMultipartFile uncheckedImage() {
    try {
      return image();
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }

  private UUID video() {
    return videos
        .saveAndFlush(
            new Video(
                UUID.randomUUID().toString().substring(0, 11),
                "영상",
                "채널",
                60,
                null,
                null,
                "[]",
                Instant.now()))
        .getId();
  }

  private UUID guide(UUID video, String state) {
    UUID job = UUID.randomUUID();
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, attempt, created_at, updated_at) values (?, ?, 'COMPLETED', 'DONE', false, 1, now(), now())",
        job,
        video);
    UUID guide = UUID.randomUUID();
    jdbc.update(
        "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input, created_at, updated_at) values (?, ?, ?, 1, ?, '{}'::jsonb, now(), now())",
        guide,
        video,
        job,
        state);
    return guide;
  }

  private <S extends Session> Login login(
      FindByIndexNameSessionRepository<S> repository, UUID user) {
    S session = repository.createSession();
    var authentication =
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(user, user + "@camera.test"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    session.setAttribute(
        HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY,
        new SecurityContextImpl(authentication));
    session.setAttribute(SessionAttributes.AUTHENTICATED_AT, Instant.now());
    repository.save(session);
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setSecure(true);
    MockHttpServletResponse response = new MockHttpServletResponse();
    cookieSerializer.writeCookieValue(
        new CookieSerializer.CookieValue(request, response, session.getId()));
    String value = response.getHeader("Set-Cookie").split(";", 2)[0];
    int equals = value.indexOf('=');
    return new Login(
        new Cookie(value.substring(0, equals), value.substring(equals + 1)), session.getId());
  }

  private record Login(Cookie cookie, String id) {}
}
