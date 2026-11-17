package com.mairor.backend.executions;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.camera.entity.FaceChecks;
import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.camera.service.FaceRegistrationExecutionService;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.security.SessionAttributes;
import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndNotifier;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.executions.dto.CreateExecutionRequest;
import com.mairor.backend.executions.entity.ExecutionStatus;
import com.mairor.backend.executions.repository.GuideExecutionOrphanRepository;
import com.mairor.backend.executions.repository.GuideExecutionRepository;
import com.mairor.backend.executions.service.ExecutionCreationService;
import com.mairor.backend.executions.service.ExecutionLifecycleService;
import com.mairor.backend.executions.service.ExecutionReplacementService;
import com.mairor.backend.executions.service.ExecutionSelectionAssembler;
import com.mairor.backend.executions.service.GuideExecutionOrphanScheduler;
import com.mairor.backend.matching.dto.CreateGuideMatchRequest;
import com.mairor.backend.matching.service.GuideMatchGenerationService;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.AuthenticatedUser;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import jakarta.servlet.http.Cookie;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
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
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.context.WebApplicationContext;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.photos.cleanup-enabled=false",
      "app.face-registration.orphan-cleanup-enabled=false",
      "app.guide-execution.orphan-cleanup-enabled=false"
    })
@AutoConfigureMockMvc
class GuideExecutionApiTest {
  private static final String PATH = "/v1/users/me/executions";
  @Autowired private WebApplicationContext context;
  @Autowired private SessionRepositoryFilter<?> sessionFilter;
  @Autowired private CookieSerializer cookieSerializer;
  @Autowired private FindByIndexNameSessionRepository<? extends Session> sessions;
  @Autowired private UserRepository users;
  @Autowired private VideoRepository videos;
  @Autowired private FaceRegistrationRepository faces;
  @Autowired private StoredPhotoRepository photos;
  @Autowired private PouchItemRepository pouch;
  @Autowired private GuideExecutionRepository executions;
  @Autowired private GuideExecutionOrphanRepository executionOrphans;
  @Autowired private GuideMatchGenerationService matching;
  @Autowired private ExecutionCreationService creation;
  @Autowired private ExecutionLifecycleService lifecycle;
  @Autowired private SessionEndNotifier sessionEnd;
  @Autowired private FaceRegistrationExecutionService faceExecutions;
  @Autowired private PlatformTransactionManager transactions;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private ObjectMapper mapper;
  @MockitoSpyBean private ExecutionReplacementService replacement;
  @MockitoSpyBean private ExecutionSelectionAssembler selectionAssembler;
  @MockitoBean private ObjectStorage storage;
  private MockMvc mvc;
  private UUID user;
  private UUID video;
  private UUID guide;
  private Login login;

  @BeforeEach
  void setUp() {
    mvc =
        MockMvcBuilders.webAppContextSetup(context)
            .addFilters(sessionFilter)
            .apply(springSecurity())
            .build();
    user = users.saveAndFlush(new User(UUID.randomUUID() + "@execution.test", "hash")).getId();
    login = login(sessions, user);
    video = video();
    guide = guide(video, "#AA4455");
    jdbc.update(
        "insert into product_categories values ('LIP', '립', true, true, 1), ('EYE', '눈', true, true, 2) on conflict do nothing");
    jdbc.update(
        "insert into product_types values ('LIPSTICK', 'LIP', '립스틱', 1), ('LIP_TINT', 'LIP', '틴트', 2), ('EYESHADOW_PALETTE', 'EYE', '팔레트', 3), ('EYELINER', 'EYE', '아이라이너', 4) on conflict do nothing");
  }

  @Test
  void createAndGetPersistTheContractAndLinkTheFaceWithoutLeakingInternalFields() throws Exception {
    UUID face = face(user, login.id(), video);
    ObjectNode body = body(match(), face, null);
    JsonNode created = created(body);
    String id = created.path("executionId").asString();
    assertThat(created.path("status").asString()).isEqualTo("IN_PROGRESS");
    assertThat(created.path("photoConsent").isNull()).isTrue();
    assertThat(created.path("recordId").isNull()).isTrue();
    assertThat(created.path("steps").size()).isEqualTo(1);
    assertThat(created.path("steps").get(0).path("skipped").asBoolean()).isTrue();
    assertThat(created.toString())
        .doesNotContain(login.id(), "storageKey", "sessionId", "compatibilityVersion");
    assertThat(faces.findById(face).orElseThrow().getExecutionId()).isEqualTo(UUID.fromString(id));
    mvc.perform(get(PATH + "/" + id).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.executionId").value(id))
        .andExpect(jsonPath("$.steps[0].noneReason").value("NO_ITEMS"));
    mvc.perform(get("/v1/users/me/face-registrations/" + face).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.executionId").value(id));
  }

  @Test
  void consentIsRecordedAndStepPhotoCanBeReplacedAndReadThroughAuthenticatedEndpoint()
      throws Exception {
    UUID selectedItem = item(user, "LIP", "LIP_TINT", "#AA4455").getId();
    UUID faceId = face(user, login.id(), video);
    String executionId =
        created(body(match(), faceId, selectedItem)).path("executionId").asString();
    MvcResult firstConsent =
        mvc.perform(
                patch(PATH + "/" + executionId + "/photo-consent")
                    .cookie(login.cookie())
                    .secure(true)
                    .with(csrf())
                    .contentType("application/json")
                    .content("{\"enabled\":true}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.enabled").value(true))
            .andExpect(jsonPath("$.policyVersion").value("v1"))
            .andReturn();
    String consentedAt =
        mapper
            .readTree(firstConsent.getResponse().getContentAsString())
            .path("consentedAt")
            .asString();
    mvc.perform(
            patch(PATH + "/" + executionId + "/photo-consent")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf())
                .contentType("application/json")
                .content("{\"enabled\":true}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.consentedAt").value(consentedAt));

    byte[] bytes = imageBytes();
    var upload =
        multipart(PATH + "/" + executionId + "/steps/lip/photo")
            .file(new MockMultipartFile("image", "capture.png", "image/png", bytes))
            .cookie(login.cookie())
            .secure(true)
            .with(csrf())
            .with(
                (RequestPostProcessor)
                    request -> {
                      request.setMethod("PUT");
                      return request;
                    });
    MvcResult uploaded =
        mvc.perform(upload)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.kind").value("STEP"))
            .andExpect(jsonPath("$.stepId").value("lip"))
            .andReturn();
    JsonNode photo = mapper.readTree(uploaded.getResponse().getContentAsString());
    UUID photoId = UUID.fromString(photo.path("photoId").asString());
    StoredPhoto stored = photos.findById(photoId).orElseThrow();
    assertThat(stored.getState()).isEqualTo(PhotoState.AVAILABLE);
    assertThat(stored.getExpiresAt()).isNull();
    assertThat(
            jdbc.queryForObject(
                "select photo_id from execution_steps where execution_id = ? and step_id = 'lip'",
                UUID.class,
                UUID.fromString(executionId)))
        .isEqualTo(photoId);
    doAnswer(
            invocation -> {
              Files.write(invocation.getArgument(1), bytes);
              return null;
            })
        .when(storage)
        .download(eq(stored.getStorageKey()), any(Path.class));
    mvc.perform(get("/v1/users/me/photos/" + photoId).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(
            (result) -> assertThat(result.getResponse().getContentAsByteArray()).isEqualTo(bytes))
        .andExpect(
            (result) ->
                assertThat(result.getResponse().getHeader("Cache-Control")).contains("no-store"));

    mvc.perform(
            patch(PATH + "/" + executionId + "/photo-consent")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf())
                .contentType("application/json")
                .content("{\"enabled\":false}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.enabled").value(false))
        .andExpect(jsonPath("$.consentedAt").doesNotExist());
    assertThat(photos.findById(photoId).orElseThrow().getState()).isEqualTo(PhotoState.AVAILABLE);
    mvc.perform(get("/v1/users/me/photos/" + photoId).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk());
    mvc.perform(upload)
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("GUIDE_PHOTO_CONSENT_REQUIRED"));
    mvc.perform(
            patch(PATH + "/" + executionId + "/photo-consent")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf())
                .contentType("application/json")
                .content("{\"enabled\":true}"))
        .andExpect(status().isOk());

    MvcResult replacementUpload = mvc.perform(upload).andExpect(status().isOk()).andReturn();
    UUID replacementId =
        UUID.fromString(
            mapper
                .readTree(replacementUpload.getResponse().getContentAsString())
                .path("photoId")
                .asString());
    assertThat(photos.findById(photoId).orElseThrow().getState()).isEqualTo(PhotoState.DELETED);
    assertThat(photos.findById(replacementId).orElseThrow().getState())
        .isEqualTo(PhotoState.AVAILABLE);
    mvc.perform(get("/v1/users/me/photos/" + photoId).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
  }

  @Test
  void stepPhotoUploadRequiresConsentAndAcceptsSkippedSteps() throws Exception {
    UUID faceId = face(user, login.id(), video);
    String executionId = created(body(match(), faceId, null)).path("executionId").asString();
    var upload =
        multipart(PATH + "/" + executionId + "/steps/lip/photo")
            .file(new MockMultipartFile("image", "capture.png", "image/png", imageBytes()))
            .cookie(login.cookie())
            .secure(true)
            .with(csrf())
            .with(
                (RequestPostProcessor)
                    request -> {
                      request.setMethod("PUT");
                      return request;
                    });
    mvc.perform(upload)
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("GUIDE_PHOTO_CONSENT_REQUIRED"));
    mvc.perform(
            patch(PATH + "/" + executionId + "/photo-consent")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf())
                .contentType("application/json")
                .content("{\"enabled\":true}"))
        .andExpect(status().isOk());
    // 제품 없이 넘긴 단계(lip)도 사진을 받는다
    mvc.perform(upload)
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.kind").value("STEP"))
        .andExpect(jsonPath("$.stepId").value("lip"));
  }

  @Test
  void stepPhotoUploadDocumentsAndReturnsUnsupportedMediaTypeAndPayloadTooLarge() throws Exception {
    UUID selectedItem = item(user, "LIP", "LIP_TINT", "#AA4455").getId();
    UUID faceId = face(user, login.id(), video);
    String executionId =
        created(body(match(), faceId, selectedItem)).path("executionId").asString();
    mvc.perform(
            patch(PATH + "/" + executionId + "/photo-consent")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf())
                .contentType("application/json")
                .content("{\"enabled\":true}"))
        .andExpect(status().isOk());

    long photoCount = photos.count();
    mvc.perform(stepPhotoUpload(executionId, new byte[] {1, 2, 3}))
        .andExpect(status().isUnsupportedMediaType())
        .andExpect(jsonPath("$.code").value("UNSUPPORTED_MEDIA_TYPE"));
    mvc.perform(stepPhotoUpload(executionId, new byte[5 * 1024 * 1024 + 1]))
        .andExpect(status().isPayloadTooLarge())
        .andExpect(jsonPath("$.code").value("PAYLOAD_TOO_LARGE"));
    assertThat(photos.count()).isEqualTo(photoCount);
  }

  private org.springframework.test.web.servlet.request.MockMultipartHttpServletRequestBuilder
      stepPhotoUpload(String executionId, byte[] content) {
    return multipart(PATH + "/" + executionId + "/steps/lip/photo")
        .file(new MockMultipartFile("image", "capture.png", "image/png", content))
        .cookie(login.cookie())
        .secure(true)
        .with(csrf())
        .with(
            (RequestPostProcessor)
                request -> {
                  request.setMethod("PUT");
                  return request;
                });
  }

  @Test
  void completionCreatesImmutableReportOnceAndRetriesAcrossSessionsWithSameRecordId()
      throws Exception {
    UUID selectedItem = item(user, "LIP", "LIP_TINT", "#AA4455").getId();
    UUID faceId = face(user, login.id(), video);
    UUID matchId = match();
    String executionId =
        created(body(matchId, faceId, selectedItem)).path("executionId").asString();
    mvc.perform(
            patch(PATH + "/" + executionId + "/photo-consent")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf())
                .contentType("application/json")
                .content("{\"enabled\":true}"))
        .andExpect(status().isOk());
    MvcResult uploadResult =
        mvc.perform(
                multipart(PATH + "/" + executionId + "/steps/lip/photo")
                    .file(new MockMultipartFile("image", "capture.png", "image/png", imageBytes()))
                    .cookie(login.cookie())
                    .secure(true)
                    .with(csrf())
                    .with(
                        (RequestPostProcessor)
                            request -> {
                              request.setMethod("PUT");
                              return request;
                            }))
            .andExpect(status().isOk())
            .andReturn();
    UUID completedPhotoId =
        UUID.fromString(
            mapper
                .readTree(uploadResult.getResponse().getContentAsString())
                .path("photoId")
                .asString());

    MvcResult first =
        mvc.perform(
                post(PATH + "/" + executionId + "/completion")
                    .cookie(login.cookie())
                    .secure(true)
                    .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("COMPLETED"))
            .andReturn();
    JsonNode completion = mapper.readTree(first.getResponse().getContentAsString());
    UUID recordId = UUID.fromString(completion.path("recordId").asString());
    assertThat(faces.findById(faceId).orElseThrow().getStatus())
        .isEqualTo(FaceRegistrationStatus.RETAINED);
    assertThat(
            jdbc.queryForObject(
                "select count(*) from history_records where execution_id = ?",
                Integer.class,
                UUID.fromString(executionId)))
        .isEqualTo(1);
    String snapshot =
        jdbc.queryForObject(
            "select record_snapshot::text from history_records where id = ?",
            String.class,
            recordId);
    JsonNode report = mapper.readTree(snapshot);
    assertThat(report.path("steps").get(0).path("matchingResult").asString())
        .isEqualTo("SUBSTITUTE");
    assertThat(report.path("completedPhoto").path("photoId").asString())
        .isEqualTo(completedPhotoId.toString());
    assertThat(report.path("substituteCount").asInt()).isEqualTo(1);

    Login anotherSession = login(sessions, user);
    mvc.perform(
            post(PATH + "/" + executionId + "/completion")
                .cookie(anotherSession.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.recordId").value(recordId.toString()))
        .andExpect(jsonPath("$.completedAt").value(completion.path("completedAt").asString()));
    assertThat(
            jdbc.queryForObject(
                "select count(*) from history_records where execution_id = ?",
                Integer.class,
                UUID.fromString(executionId)))
        .isEqualTo(1);
  }

  @Test
  void completionWithoutProductsOrPhotosStillCreatesReportWithNullCompletedPhoto()
      throws Exception {
    UUID faceId = face(user, login.id(), video);
    String executionId = created(body(match(), faceId, null)).path("executionId").asString();
    MvcResult completed =
        mvc.perform(
                post(PATH + "/" + executionId + "/completion")
                    .cookie(login.cookie())
                    .secure(true)
                    .with(csrf()))
            .andExpect(status().isCreated())
            .andReturn();
    UUID recordId =
        UUID.fromString(
            mapper
                .readTree(completed.getResponse().getContentAsString())
                .path("recordId")
                .asString());
    JsonNode report =
        mapper.readTree(
            jdbc.queryForObject(
                "select record_snapshot::text from history_records where id = ?",
                String.class,
                recordId));
    assertThat(report.path("completedPhoto").isNull()).isTrue();
    assertThat(report.path("steps").get(0).path("matchingResult").asString()).isEqualTo("NONE");
    assertThat(report.path("steps").get(0).path("selectedProduct").isNull()).isTrue();
    assertThat(faces.findById(faceId).orElseThrow().getStatus())
        .isEqualTo(FaceRegistrationStatus.RETAINED);
  }

  @Test
  void completedPhotoIsTheLatestStepPhotoEvenWhenTheLastStepHasNone() throws Exception {
    jdbc.update(
        "update guides set guide_input = jsonb_set(guide_input, '{steps,2}', '{\"stepId\":\"eye\",\"order\":2,\"makeup\":\"eyeshadow\"}'::jsonb) where id = ?",
        guide);
    UUID faceId = face(user, login.id(), video);
    ObjectNode body = body(match(), faceId, null);
    ObjectNode eye = ((ArrayNode) body.path("selections")).addObject();
    eye.put("stepId", "eye");
    eye.putNull("selectedPouchItemId");
    String executionId = created(body).path("executionId").asString();
    mvc.perform(
            patch(PATH + "/" + executionId + "/photo-consent")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf())
                .contentType("application/json")
                .content("{\"enabled\":true}"))
        .andExpect(status().isOk());
    String eyePhoto = uploadStepPhoto(executionId, "eye");
    String lipPhoto = uploadStepPhoto(executionId, "lip");
    assertThat(lipPhoto).isNotEqualTo(eyePhoto);

    JsonNode report = completedReport(executionId);
    assertThat(report.path("completedPhoto").path("photoId").asString()).isEqualTo(lipPhoto);
    assertThat(report.path("steps").get(1).path("photo").path("photoId").asString())
        .isEqualTo(eyePhoto);
  }

  private String uploadStepPhoto(String executionId, String stepId) throws Exception {
    MvcResult result =
        mvc.perform(
                multipart(PATH + "/" + executionId + "/steps/" + stepId + "/photo")
                    .file(new MockMultipartFile("image", "capture.png", "image/png", imageBytes()))
                    .cookie(login.cookie())
                    .secure(true)
                    .with(csrf())
                    .with(
                        (RequestPostProcessor)
                            request -> {
                              request.setMethod("PUT");
                              return request;
                            }))
            .andExpect(status().isOk())
            .andReturn();
    return mapper.readTree(result.getResponse().getContentAsString()).path("photoId").asString();
  }

  private JsonNode completedReport(String executionId) throws Exception {
    MvcResult completed =
        mvc.perform(
                post(PATH + "/" + executionId + "/completion")
                    .cookie(login.cookie())
                    .secure(true)
                    .with(csrf()))
            .andExpect(status().isCreated())
            .andReturn();
    String recordId =
        mapper.readTree(completed.getResponse().getContentAsString()).path("recordId").asString();
    return mapper.readTree(
        jdbc.queryForObject(
            "select record_snapshot::text from history_records where id = ?",
            String.class,
            UUID.fromString(recordId)));
  }

  @Test
  void abandonmentBlocksPhotosIsIdempotentAndRejectsCompletedRuns() throws Exception {
    PouchItem selected = item(user, "LIP", "LIPSTICK", "#AA4455");
    UUID faceId = face(user, login.id(), video);
    String executionId =
        created(body(match(), faceId, selected.getId())).path("executionId").asString();
    StoredPhoto stepPhoto = photo(user, login.id(), PhotoKind.STEP, "lip");
    jdbc.update(
        "update execution_steps set photo_id = ? where execution_id = ?",
        stepPhoto.getId(),
        UUID.fromString(executionId));

    mvc.perform(
            post(PATH + "/" + executionId + "/abandonment")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("ABANDONED"))
        .andExpect(jsonPath("$.cleanupPending").value(false));
    assertThat(executions.findById(UUID.fromString(executionId)).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.ABANDONED);
    assertThat(faces.findById(faceId).orElseThrow().getDiscardedAt()).isNotNull();
    assertThat(photos.findById(stepPhoto.getId()).orElseThrow().getState())
        .isEqualTo(PhotoState.DELETED);
    mvc.perform(get("/v1/users/me/photos/" + stepPhoto.getId()).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());

    mvc.perform(
            post(PATH + "/" + executionId + "/abandonment")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.cleanupPending").value(false));
    mvc.perform(
            post(PATH + "/" + executionId + "/completion")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isConflict());

    String completedId =
        created(body(match(), face(user, login.id(), video), null)).path("executionId").asString();
    mvc.perform(
            post(PATH + "/" + completedId + "/completion")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isCreated());
    mvc.perform(
            post(PATH + "/" + completedId + "/abandonment")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("GUIDE_EXECUTION_ALREADY_COMPLETED"));
  }

  @Test
  void failedObjectDeletionKeepsPhotosBlockedAndReportsPendingCleanup() throws Exception {
    PouchItem selected = item(user, "LIP", "LIPSTICK", "#AA4455");
    UUID faceId = face(user, login.id(), video);
    String executionId =
        created(body(match(), faceId, selected.getId())).path("executionId").asString();
    StoredPhoto stepPhoto = photo(user, login.id(), PhotoKind.STEP, "lip");
    jdbc.update(
        "update execution_steps set photo_id = ? where execution_id = ?",
        stepPhoto.getId(),
        UUID.fromString(executionId));
    doThrow(new StorageException("temporary delete failure", null))
        .when(storage)
        .delete(anyString());

    mvc.perform(
            post(PATH + "/" + executionId + "/abandonment")
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.cleanupPending").value(true));
    assertThat(photos.findById(stepPhoto.getId()).orElseThrow().getState())
        .isEqualTo(PhotoState.CLEANUP_PENDING);
    mvc.perform(get("/v1/users/me/photos/" + stepPhoto.getId()).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
  }

  @Test
  void sessionEndAbandonsOnlyThatSessionsInProgressExecutions() throws Exception {
    UUID matchId = match();
    UUID sameSessionFace = face(user, login.id(), video);
    UUID sameSessionExecution =
        UUID.fromString(
            created(body(matchId, sameSessionFace, null)).path("executionId").asString());
    Login other = login(sessions, user);
    UUID otherFace = face(user, other.id(), video);
    UUID otherSessionExecution =
        creation
            .create(
                user,
                other.id(),
                mapper.treeToValue(body(matchId, otherFace, null), CreateExecutionRequest.class))
            .executionId();

    sessionEnd.strict(new SessionEnd(user.toString(), login.id(), SessionEndReason.LOGOUT));

    assertThat(executions.findById(sameSessionExecution).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.ABANDONED);
    assertThat(faces.findById(sameSessionFace).orElseThrow().getDiscardedAt()).isNotNull();
    assertThat(executions.findById(otherSessionExecution).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.IN_PROGRESS);
  }

  @Test
  void orphanSweepRecoversRunsWhoseSessionRowsAreAlreadyGone() throws Exception {
    UUID matchId = match();
    UUID lostSessionFace = face(user, login.id(), video);
    UUID lostSessionExecution =
        UUID.fromString(
            created(body(matchId, lostSessionFace, null)).path("executionId").asString());
    Login active = login(sessions, user);
    UUID activeFace = face(user, active.id(), video);
    UUID activeExecution =
        creation
            .create(
                user,
                active.id(),
                mapper.treeToValue(body(matchId, activeFace, null), CreateExecutionRequest.class))
            .executionId();

    sessions.deleteById(login.id());
    new GuideExecutionOrphanScheduler(executionOrphans, lifecycle, 50).sweep();

    assertThat(executions.findById(lostSessionExecution).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.ABANDONED);
    assertThat(faces.findById(lostSessionFace).orElseThrow().getDiscardedAt()).isNotNull();
    assertThat(executions.findById(activeExecution).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.IN_PROGRESS);
    assertThat(faces.findById(activeFace).orElseThrow().getDiscardedAt()).isNull();
  }

  @Test
  void guideStepsMustBeSelectedExactlyOnceAndExcludedStepsCannotBeSelected() throws Exception {
    UUID face = face(user, login.id(), video);
    UUID match = match();
    for (String selections :
        List.of(
            "[]",
            "[{\"stepId\":\"skin\",\"selectedPouchItemId\":null}]",
            "[{\"stepId\":\"lip\",\"selectedPouchItemId\":null},{\"stepId\":\"lip\",\"selectedPouchItemId\":null}]")) {
      ObjectNode body = body(match, face, null);
      body.set("selections", mapper.readTree(selections));
      send(body)
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("GUIDE_SELECTION_INVALID"));
    }
    assertThat(faces.findById(face).orElseThrow().getStatus())
        .isEqualTo(FaceRegistrationStatus.REGISTERED);
    assertThat(executionCount()).isZero();
  }

  @Test
  void requiredFieldsNullEntriesAndMalformedIdsAreRejected() throws Exception {
    ObjectNode valid = body(match(), face(user, login.id(), video), null);
    for (String field :
        List.of(
            "guideId", "matchId", "faceRegistrationId", "selections", "acceptMissingProducts")) {
      ObjectNode broken = valid.deepCopy();
      broken.remove(field);
      send(broken)
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    }
    ObjectNode broken = valid.deepCopy();
    ((ObjectNode) broken.path("selections").get(0)).remove("selectedPouchItemId");
    send(broken).andExpect(status().isBadRequest());
    broken = valid.deepCopy();
    broken.set("selections", mapper.readTree("[null]"));
    send(broken).andExpect(status().isBadRequest());
    broken = valid.deepCopy();
    broken.put("guideId", "invalid-id");
    send(broken).andExpect(status().isBadRequest());
    assertThat(executionCount()).isZero();
  }

  @Test
  void authenticationCsrfAndOriginalSessionAreEnforced() throws Exception {
    ObjectNode body = body(match(), face(user, login.id(), video), null);
    mvc.perform(
            post(PATH)
                .secure(true)
                .with(csrf())
                .contentType("application/json")
                .content(body.toString()))
        .andExpect(status().isUnauthorized());
    mvc.perform(
            post(PATH)
                .cookie(login.cookie())
                .secure(true)
                .contentType("application/json")
                .content(body.toString()))
        .andExpect(status().isForbidden());
    String id = created(body).path("executionId").asString();
    mvc.perform(get(PATH + "/" + id).secure(true)).andExpect(status().isUnauthorized());
    Login otherSession = login(sessions, user);
    mvc.perform(get(PATH + "/" + id).cookie(otherSession.cookie()).secure(true))
        .andExpect(status().isNotFound());
    UUID other =
        users.saveAndFlush(new User(UUID.randomUUID() + "@execution.test", "hash")).getId();
    mvc.perform(get(PATH + "/" + id).cookie(login(sessions, other).cookie()).secure(true))
        .andExpect(status().isNotFound());
    assertThat(executionCount()).isEqualTo(1);
  }

  @Test
  void privateOwnershipFailuresWinOverStaleAndInvalidSelectionErrors() throws Exception {
    UUID other =
        users.saveAndFlush(new User(UUID.randomUUID() + "@execution.test", "hash")).getId();
    UUID foreignItem = item(other, "LIP", "LIPSTICK", "#AA4455").getId();
    UUID face = face(user, login.id(), video);
    UUID match = match();
    jdbc.update("update users set pouch_version = pouch_version + 1 where id = ?", user);
    send(body(match, face, foreignItem)).andExpect(status().isNotFound());
    send(body(match, face(other, login.id(), video), null)).andExpect(status().isNotFound());
    send(body(matching.create(other, new CreateGuideMatchRequest(guide)).matchId(), face, null))
        .andExpect(status().isNotFound());
    Login otherSession = login(sessions, user);
    send(body(match, face(user, otherSession.id(), video), null)).andExpect(status().isNotFound());
    assertThat(executionCount()).isZero();
  }

  @ParameterizedTest
  @ValueSource(strings = {"pouch", "guide", "reference", "compatibility", "review"})
  void staleSnapshotsAreRejectedWithoutConsumingTheFace(String version) throws Exception {
    UUID match = match();
    UUID face = face(user, login.id(), video);
    switch (version) {
      case "pouch" ->
          jdbc.update("update users set pouch_version = pouch_version + 1 where id = ?", user);
      case "guide" -> jdbc.update("update guides set version = version + 1 where id = ?", guide);
      case "reference" ->
          jdbc.update(
              "update guides set reference_version = reference_version + 1 where id = ?", guide);
      case "compatibility" ->
          jdbc.update("update guide_matches set compatibility_version = 999 where id = ?", match);
      case "review" ->
          jdbc.update("update guides set review_status = 'REJECTED' where id = ?", guide);
      default -> throw new AssertionError();
    }
    send(body(match, face, null))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("GUIDE_MATCH_STALE"));
    assertThat(faces.findById(face).orElseThrow().getStatus())
        .isEqualTo(FaceRegistrationStatus.REGISTERED);
    assertThat(executionCount()).isZero();
  }

  @Test
  void wrongVideoOrWrongGuideMatchCannotStartAnExecution() throws Exception {
    UUID match = match();
    UUID differentVideo = video();
    send(body(match, face(user, login.id(), differentVideo), null))
        .andExpect(status().isNotFound());
    ObjectNode wrongGuide = body(match, face(user, login.id(), video), null);
    wrongGuide.put("guideId", guide(differentVideo, null).toString());
    send(wrongGuide).andExpect(status().isNotFound());
  }

  @Test
  void choosingNoneRequiresAcknowledgmentAndRecordsNotSelected() throws Exception {
    item(user, "LIP", "LIPSTICK", "#AA4455");
    UUID match = match();
    UUID face = face(user, login.id(), video);
    ObjectNode body = body(match, face, null);
    body.put("acceptMissingProducts", false);
    send(body)
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("GUIDE_MISSING_PRODUCTS_NOT_ACKNOWLEDGED"));
    body.put("acceptMissingProducts", true);
    JsonNode snapshot = created(body).path("steps").get(0);
    assertThat(snapshot.path("result").asString()).isEqualTo("NONE");
    assertThat(snapshot.path("noneReason").asString()).isEqualTo("NOT_SELECTED");
    assertThat(snapshot.path("candidates").size()).isEqualTo(1);
  }

  @Test
  void invalidCategoryAndColorlessSubstitutesAreRejected() throws Exception {
    PouchItem wrongCategory = item(user, "EYE", "EYELINER", "#AA4455");
    PouchItem colorless = item(user, "LIP", "LIPSTICK", null);
    UUID match = match();
    UUID face = face(user, login.id(), video);
    for (UUID selected : List.of(wrongCategory.getId(), colorless.getId())) {
      send(body(match, face, selected))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("GUIDE_SELECTION_INVALID"));
    }
    assertThat(executionCount()).isZero();
  }

  @Test
  void snapshotSurvivesPouchDeletionAndGuideChanges() throws Exception {
    PouchItem selected = item(user, "LIP", "LIPSTICK", "#AA4455");
    String name = selected.getName();
    JsonNode created = created(body(match(), face(user, login.id(), video), selected.getId()));
    String execution = created.path("executionId").asString();
    assertThat(created.path("steps").get(0).path("selectedColor").path("hex").asString())
        .isEqualTo("#AA4455");
    pouch.deleteById(selected.getId());
    jdbc.update(
        "update guides set version = version + 1, guide_input = '{\"steps\":[]}'::jsonb where id = ?",
        guide);
    mvc.perform(get(PATH + "/" + execution).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.guideVersion").value(1))
        .andExpect(jsonPath("$.steps[0].selectedProduct.name").value(name))
        .andExpect(jsonPath("$.steps[0].selectedColor.hex").value("#AA4455"));
  }

  @Test
  void sameFaceRetryAndConcurrentStartsCreateOnlyOneExecution() throws Exception {
    UUID face = face(user, login.id(), video);
    ObjectNode body = body(match(), face, null);
    CreateExecutionRequest request = mapper.treeToValue(body, CreateExecutionRequest.class);
    try (var executor = Executors.newFixedThreadPool(2)) {
      var one = executor.submit(() -> startResult(request));
      var two = executor.submit(() -> startResult(request));
      assertThat(List.of(one.get(15, TimeUnit.SECONDS), two.get(15, TimeUnit.SECONDS)))
          .containsExactlyInAnyOrder("CREATED", "FACE_REGISTRATION_ALREADY_USED");
    }
    send(body)
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("FACE_REGISTRATION_ALREADY_USED"));
    assertThat(executionCount()).isEqualTo(1);
    assertThat(
            jdbc.queryForObject(
                "select count(*) from guide_executions where user_id = ? and status = 'IN_PROGRESS'",
                Integer.class,
                user))
        .isEqualTo(1);
  }

  @Test
  void successfulReplacementBlocksThePreviousExecutionAndSchedulesItsPhotos() throws Exception {
    PouchItem selected = item(user, "LIP", "LIPSTICK", "#AA4455");
    UUID match = match();
    UUID firstFace = face(user, login.id(), video);
    UUID first =
        UUID.fromString(
            created(body(match, firstFace, selected.getId())).path("executionId").asString());
    StoredPhoto stepPhoto = photo(user, login.id(), PhotoKind.STEP, "lip");
    jdbc.update(
        "update execution_steps set photo_id = ? where execution_id = ?", stepPhoto.getId(), first);
    jdbc.update(
        "update guide_executions set photo_consent = true, consent_policy_version = 'v1', consented_at = now() where id = ?",
        first);
    UUID secondFace = face(user, login.id(), video);
    UUID second =
        UUID.fromString(
            created(body(match, secondFace, selected.getId())).path("executionId").asString());
    assertThat(executions.findById(first).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.ABANDONED);
    assertThat(executions.findById(second).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.IN_PROGRESS);
    assertThat(photos.findById(stepPhoto.getId()).orElseThrow().getState())
        .isEqualTo(PhotoState.CLEANUP_PENDING);
    assertThat(
            photos
                .findById(faces.findById(firstFace).orElseThrow().getPhotoId())
                .orElseThrow()
                .getState())
        .isEqualTo(PhotoState.CLEANUP_PENDING);
    mvc.perform(get(PATH + "/" + first).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
  }

  @Test
  void failedReplacementRollsBackTheNewExecutionAndPreservesTheOldOne() throws Exception {
    UUID match = match();
    UUID oldFace = face(user, login.id(), video);
    UUID old = UUID.fromString(created(body(match, oldFace, null)).path("executionId").asString());
    UUID newFace = face(user, login.id(), video);
    ExecutionReplacementService replacementTarget =
        AopTestUtils.getUltimateTargetObject(replacement);
    doAnswer(
            invocation -> {
              invocation.callRealMethod();
              throw new IllegalStateException("simulated failure after cleanup scheduling");
            })
        .when(replacementTarget)
        .abandon(any());
    CreateExecutionRequest request =
        mapper.treeToValue(body(match, newFace, null), CreateExecutionRequest.class);
    assertThatThrownBy(() -> creation.create(user, login.id(), request))
        .isInstanceOf(IllegalStateException.class);
    assertThat(executionCount()).isEqualTo(1);
    assertThat(executions.findById(old).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.IN_PROGRESS);
    assertThat(faces.findById(oldFace).orElseThrow().getDiscardedAt()).isNull();
    assertThat(
            photos
                .findById(faces.findById(oldFace).orElseThrow().getPhotoId())
                .orElseThrow()
                .getState())
        .isEqualTo(PhotoState.AVAILABLE);
    assertThat(faces.findById(newFace).orElseThrow().getStatus())
        .isEqualTo(FaceRegistrationStatus.REGISTERED);
  }

  @Test
  void completedAndOtherSessionExecutionsSurviveANewStart() throws Exception {
    UUID match = match();
    UUID originalFace = face(user, login.id(), video);
    UUID completed =
        UUID.fromString(created(body(match, originalFace, null)).path("executionId").asString());
    new TransactionTemplate(transactions)
        .executeWithoutResult(
            status -> {
              executions
                  .findById(completed)
                  .orElseThrow()
                  .complete(UUID.randomUUID(), Instant.now());
              faceExecutions.retain(user, login.id(), originalFace, completed);
            });
    Login other = login(sessions, user);
    var otherRequest =
        mapper.treeToValue(
            body(match, face(user, other.id(), video), null), CreateExecutionRequest.class);
    UUID otherExecution = creation.create(user, other.id(), otherRequest).executionId();
    created(body(match, face(user, login.id(), video), null));
    assertThat(executions.findById(completed).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.COMPLETED);
    assertThat(executions.findById(otherExecution).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.IN_PROGRESS);
    mvc.perform(get(PATH + "/" + completed).cookie(other.cookie()).secure(true))
        .andExpect(status().isOk());
  }

  @Test
  void sameProductNeedsNoColorAndUsesTheOriginalSlotWhenOneIsLinked() throws Exception {
    Catalog original = catalog("LIP", "LIPSTICK");
    link(original, null);
    PouchItem selected = catalogItem(original, "LIP", "LIPSTICK");
    JsonNode first =
        created(body(match(), face(user, login.id(), video), selected.getId()))
            .path("steps")
            .get(0);
    assertThat(first.path("result").asString()).isEqualTo("SAME");
    assertThat(first.path("selectedColorId").isNull()).isTrue();
    UUID slot = slot(original.shade(), 0, "#AA4455", "AUTO_APPROVED");
    jdbc.update(
        "update guide_step_product_links set color_id = ?, match_level = 'SLOT' where guide_id = ?",
        slot,
        guide);
    JsonNode second =
        created(body(match(), face(user, login.id(), video), selected.getId()))
            .path("steps")
            .get(0);
    assertThat(second.path("result").asString()).isEqualTo("SAME");
    assertThat(second.path("selectedColorId").asString()).isEqualTo(slot.toString());
    assertThat(second.path("selectedColor").path("hex").asString()).isEqualTo("#AA4455");
  }

  @Test
  void invalidNewSelectionLeavesTheExistingExecutionAndItsFaceUntouched() throws Exception {
    UUID match = match();
    UUID previousFace = face(user, login.id(), video);
    UUID previous =
        UUID.fromString(created(body(match, previousFace, null)).path("executionId").asString());
    UUID nextFace = face(user, login.id(), video);
    ObjectNode invalid = body(match, nextFace, null);
    ((ObjectNode) invalid.path("selections").get(0)).put("stepId", "skin");
    send(invalid).andExpect(status().isBadRequest());
    assertThat(executionCount()).isEqualTo(1);
    assertThat(executions.findById(previous).orElseThrow().getStatus())
        .isEqualTo(ExecutionStatus.IN_PROGRESS);
    assertThat(faces.findById(previousFace).orElseThrow().getDiscardedAt()).isNull();
    assertThat(faces.findById(nextFace).orElseThrow().getStatus())
        .isEqualTo(FaceRegistrationStatus.REGISTERED);
  }

  @Test
  void getReturnsCurrentPhotoMetadataAndHidesCleanupPendingPhotos() throws Exception {
    PouchItem selected = item(user, "LIP", "LIPSTICK", "#AA4455");
    UUID execution =
        UUID.fromString(
            created(body(match(), face(user, login.id(), video), selected.getId()))
                .path("executionId")
                .asString());
    StoredPhoto photo = photo(user, login.id(), PhotoKind.STEP, "lip");
    jdbc.update(
        "update execution_steps set photo_id = ? where execution_id = ?", photo.getId(), execution);
    mvc.perform(get(PATH + "/" + execution).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(
            org.springframework.test.web.servlet.result.MockMvcResultMatchers.header()
                .string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.steps[0].photo.photoId").value(photo.getId().toString()))
        .andExpect(jsonPath("$.steps[0].photo.kind").value("STEP"))
        .andExpect(jsonPath("$.steps[0].photo.storageKey").doesNotExist());
    photo.requestCleanup(Instant.now());
    photos.saveAndFlush(photo);
    mvc.perform(get(PATH + "/" + execution).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.steps[0].photo").isEmpty());
  }

  @Test
  void manualSelectionRejectsSameCategoryButIncompatibleType() throws Exception {
    jdbc.update(
        "insert into product_types values ('LIP_OTHER', 'LIP', '기타 립', 10) on conflict do nothing");
    PouchItem selected = item(user, "LIP", "LIP_OTHER", "#AA4455");
    send(body(match(), face(user, login.id(), video), selected.getId()))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("GUIDE_SELECTION_INVALID"));
    assertThat(executionCount()).isZero();
  }

  @Test
  void candidateUsesItsSavedColorSlotRatherThanRecalculatingTheNearestSlot() throws Exception {
    Catalog palette = catalog("LIP", "LIPSTICK");
    slot(palette.shade(), 0, "#AA4455", "AUTO_APPROVED");
    UUID savedSlot = slot(palette.shade(), 1, "#000000", "AUTO_APPROVED");
    PouchItem selected = catalogItem(palette, "LIP", "LIPSTICK");
    UUID match = match();
    // 이전 서버 정책이 이 칸을 선택한 저장 스냅샷으로 만든다. 실행은 이를 재랭킹하면 안 된다.
    jdbc.update(
        "update guide_matches set match_snapshot = jsonb_set(jsonb_set(match_snapshot, '{steps,0,candidates,0,matchedColorId}', to_jsonb(?::text)), '{steps,0,candidates,0,product,color,hex}', '\"#000000\"'::jsonb) where id = ?",
        savedSlot.toString(),
        match);
    JsonNode snapshot =
        created(body(match, face(user, login.id(), video), selected.getId())).path("steps").get(0);
    assertThat(snapshot.path("selectedColorId").asString()).isEqualTo(savedSlot.toString());
    assertThat(snapshot.path("selectedColor").path("hex").asString()).isEqualTo("#000000");
    assertThat(snapshot.path("candidates").get(0).path("matchedColorId").asString())
        .isEqualTo(savedSlot.toString());
  }

  @Test
  void manualPaletteOutsideTheThreeCandidatesUsesTheClosestUsableSlot() throws Exception {
    item(user, "LIP", "LIPSTICK", "#AA4455");
    item(user, "LIP", "LIPSTICK", "#AA4455");
    item(user, "LIP", "LIPSTICK", "#AA4455");
    Catalog palette = catalog("LIP", "LIPSTICK");
    slot(palette.shade(), 0, "#AA4455", "REJECTED");
    UUID expected = slot(palette.shade(), 1, "#AA4456", "AUTO_APPROVED");
    slot(palette.shade(), 2, "#000000", "AUTO_APPROVED");
    PouchItem selected = catalogItem(palette, "LIP", "LIPSTICK");
    JsonNode snapshot =
        created(body(match(), face(user, login.id(), video), selected.getId()))
            .path("steps")
            .get(0);
    assertThat(snapshot.path("result").asString()).isEqualTo("SUBSTITUTE");
    assertThat(snapshot.path("selectedColorId").asString()).isEqualTo(expected.toString());
    assertThat(snapshot.path("selectedColor").path("hex").asString()).isEqualTo("#AA4456");
    assertThat(snapshot.path("candidates").size()).isEqualTo(3);
    assertThat(snapshot.path("candidates").toString()).doesNotContain(selected.getId().toString());
  }

  @Test
  void missingReferenceKeepsTheSelectedProductButLeavesTheColorUnset() throws Exception {
    jdbc.update(
        "update guides set guide_input = jsonb_set(guide_input, '{steps,1,targetColor}', 'null'::jsonb) where id = ?",
        guide);
    PouchItem selected = item(user, "LIP", "LIP_TINT", "#AA4455");
    JsonNode snapshot =
        created(body(match(), face(user, login.id(), video), selected.getId()))
            .path("steps")
            .get(0);
    assertThat(snapshot.path("result").asString()).isEqualTo("SUBSTITUTE");
    assertThat(snapshot.path("selectedProduct").path("pouchItemId").asString())
        .isEqualTo(selected.getId().toString());
    assertThat(snapshot.path("selectedColorId").isNull()).isTrue();
    assertThat(snapshot.path("selectedColor").isNull()).isTrue();
  }

  @Test
  void concurrentStartsWithDifferentFacesReplaceOnlyTheSameSessionsActiveExecution()
      throws Exception {
    UUID firstGuide = guide;
    UUID firstFace = face(user, login.id(), video);
    var firstRequest =
        mapper.treeToValue(body(match(), firstFace, null), CreateExecutionRequest.class);
    UUID secondVideo = video();
    guide = guide(secondVideo, "#AA4455");
    var secondRequest =
        mapper.treeToValue(
            body(match(), face(user, login.id(), secondVideo), null), CreateExecutionRequest.class);
    try (var executor = Executors.newFixedThreadPool(2)) {
      var one = executor.submit(() -> creation.create(user, login.id(), firstRequest));
      var two = executor.submit(() -> creation.create(user, login.id(), secondRequest));
      one.get(15, TimeUnit.SECONDS);
      two.get(15, TimeUnit.SECONDS);
    }
    assertThat(executionCount()).isEqualTo(2);
    assertThat(
            jdbc.queryForObject(
                "select count(*) from guide_executions where user_id = ? and status = 'IN_PROGRESS'",
                Integer.class,
                user))
        .isEqualTo(1);
    assertThat(
            jdbc.queryForObject(
                "select count(*) from guide_executions where user_id = ? and status = 'ABANDONED'",
                Integer.class,
                user))
        .isEqualTo(1);
    guide = firstGuide;
  }

  @Test
  void guideVersionChangesWaitUntilTheExecutionSnapshotHasCommitted() throws Exception {
    UUID face = face(user, login.id(), video);
    var request = mapper.treeToValue(body(match(), face, null), CreateExecutionRequest.class);
    CountDownLatch locked = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    CountDownLatch writerStarted = new CountDownLatch(1);
    CountDownLatch writerFinished = new CountDownLatch(1);
    doAnswer(
            invocation -> {
              Object result = invocation.callRealMethod();
              locked.countDown();
              if (!release.await(10, TimeUnit.SECONDS))
                throw new AssertionError("guide lock release timeout");
              return result;
            })
        .when(selectionAssembler)
        .verifyOwnership(any(), any());
    try (var executor = Executors.newFixedThreadPool(2)) {
      var created = executor.submit(() -> creation.create(user, login.id(), request));
      assertThat(locked.await(10, TimeUnit.SECONDS)).isTrue();
      var changed =
          executor.submit(
              () -> {
                writerStarted.countDown();
                jdbc.update(
                    "update guides set reference_version = reference_version + 1 where id = ?",
                    guide);
                writerFinished.countDown();
              });
      try {
        assertThat(writerStarted.await(5, TimeUnit.SECONDS)).isTrue();
        assertThat(writerFinished.await(200, TimeUnit.MILLISECONDS)).isFalse();
      } finally {
        release.countDown();
      }
      assertThat(created.get(10, TimeUnit.SECONDS).guideVersion()).isEqualTo(1);
      changed.get(10, TimeUnit.SECONDS);
    } finally {
      release.countDown();
    }
    assertThat(executionCount()).isEqualTo(1);
  }

  private Catalog catalog(String category, String type) {
    UUID product = UUID.randomUUID();
    UUID shade = UUID.randomUUID();
    jdbc.update(
        "insert into products (id, brand, name, brand_normalized, name_normalized, category_code, type_code, created_at, updated_at) values (?, '브랜드', ?, '브랜드', ?, ?, ?, now(), now())",
        product,
        product.toString(),
        product.toString(),
        category,
        type);
    jdbc.update(
        "insert into product_shades (id, product_id, name, name_normalized, sort_order, created_at, updated_at) values (?, ?, '호수', '호수', 0, now(), now())",
        shade,
        product);
    return new Catalog(product, shade);
  }

  private PouchItem catalogItem(Catalog catalog, String category, String type) {
    return pouch.saveAndFlush(
        new PouchItem(
            user,
            RegistrationMode.CATALOG,
            catalog.product(),
            catalog.shade(),
            category,
            type,
            "브랜드",
            catalog.product().toString(),
            "호수",
            null));
  }

  private UUID slot(UUID shade, int order, String hex, String review) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into product_shade_colors (id, shade_id, sort_order, name_source, color_hex, color_source, color_estimated, review_status, created_at, updated_at) values (?, ?, ?, 'NONE', ?, 'SAMPLE', false, ?, now(), now())",
        id,
        shade,
        order,
        hex,
        review);
    return id;
  }

  private void link(Catalog catalog, UUID color) {
    jdbc.update(
        "insert into guide_step_product_links (id, guide_id, step_id, product_id, shade_id, color_id, match_level, created_at, updated_at) values (?, ?, 'lip', ?, ?, ?, ?, now(), now())",
        UUID.randomUUID(),
        guide,
        catalog.product(),
        catalog.shade(),
        color,
        color == null ? "SHADE" : "SLOT");
  }

  private record Catalog(UUID product, UUID shade) {}

  private org.springframework.test.web.servlet.ResultActions send(ObjectNode body)
      throws Exception {
    return mvc.perform(
        post(PATH)
            .cookie(login.cookie())
            .secure(true)
            .with(csrf())
            .contentType("application/json")
            .content(body.toString()));
  }

  private JsonNode created(ObjectNode body) throws Exception {
    MvcResult result = send(body).andExpect(status().isCreated()).andReturn();
    return mapper.readTree(result.getResponse().getContentAsString());
  }

  private String startResult(CreateExecutionRequest request) {
    try {
      creation.create(user, login.id(), request);
      return "CREATED";
    } catch (BusinessException failure) {
      return failure.code();
    }
  }

  private ObjectNode body(UUID match, UUID face, UUID selected) {
    ObjectNode body = mapper.createObjectNode();
    body.put("guideId", guide.toString());
    body.put("matchId", match.toString());
    body.put("faceRegistrationId", face.toString());
    ObjectNode selection = body.putArray("selections").addObject();
    selection.put("stepId", "lip");
    if (selected == null) selection.putNull("selectedPouchItemId");
    else selection.put("selectedPouchItemId", selected.toString());
    body.put("acceptMissingProducts", true);
    return body;
  }

  private UUID match() {
    return matching.create(user, new CreateGuideMatchRequest(guide)).matchId();
  }

  private int executionCount() {
    return jdbc.queryForObject(
        "select count(*) from guide_executions where user_id = ?", Integer.class, user);
  }

  private PouchItem item(UUID owner, String category, String type, String hex) {
    return pouch.saveAndFlush(
        new PouchItem(
            owner,
            RegistrationMode.MANUAL,
            null,
            null,
            category,
            type,
            "브랜드",
            UUID.randomUUID().toString(),
            null,
            hex == null ? null : PouchColor.userInput(hex)));
  }

  private UUID face(UUID owner, String session, UUID video) {
    return faces
        .saveAndFlush(
            new FaceRegistration(
                photo(owner, session, PhotoKind.FACE_REGISTRATION, null),
                video,
                null,
                new FaceChecks(true, true, true, true, false),
                "v1",
                Instant.now()))
        .getId();
  }

  private StoredPhoto photo(UUID owner, String session, PhotoKind kind, String step) {
    StoredPhoto photo =
        new StoredPhoto(
            owner, session, kind, step, "photos/" + UUID.randomUUID(), "image/png", 10, 2, 2, null);
    photo.markAvailable();
    return photos.saveAndFlush(photo);
  }

  private byte[] imageBytes() throws Exception {
    BufferedImage image = new BufferedImage(3, 2, BufferedImage.TYPE_INT_RGB);
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    javax.imageio.ImageIO.write(image, "png", output);
    image.flush();
    return output.toByteArray();
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

  private UUID guide(UUID video, String referenceHex) {
    UUID job = UUID.randomUUID();
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, attempt, created_at, updated_at) values (?, ?, 'COMPLETED', 'DONE', false, 1, now(), now())",
        job,
        video);
    UUID guide = UUID.randomUUID();
    String input =
        "{\"steps\":[{\"stepId\":\"skin\",\"order\":0,\"makeup\":\"other\"},{\"stepId\":\"lip\",\"order\":1,\"makeup\":\"lip\",\"targetColor\":"
            + (referenceHex == null ? "null" : "{\"hex\":\"" + referenceHex + "\"}")
            + ",\"product\":{\"brand\":\"영상 브랜드\",\"name\":\"영상 제품\"}}]}";
    jdbc.update(
        "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input, created_at, updated_at) values (?, ?, ?, 1, 'APPROVED', ?::jsonb, now(), now())",
        guide,
        video,
        job,
        input);
    return guide;
  }

  private <S extends Session> Login login(
      FindByIndexNameSessionRepository<S> repository, UUID user) {
    S session = repository.createSession();
    var authentication =
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(user, user + "@execution.test"),
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
    String cookie = response.getHeader("Set-Cookie").split(";", 2)[0];
    int equals = cookie.indexOf('=');
    return new Login(
        new Cookie(cookie.substring(0, equals), cookie.substring(equals + 1)), session.getId());
  }

  private record Login(Cookie cookie, String id) {}
}
