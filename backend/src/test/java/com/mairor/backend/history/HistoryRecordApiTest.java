package com.mairor.backend.history;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.camera.entity.FaceChecks;
import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.common.security.SessionAttributes;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.matching.dto.CreateGuideMatchRequest;
import com.mairor.backend.matching.service.GuideMatchGenerationService;
import com.mairor.backend.photos.entity.PhotoKind;
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
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
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
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * 리포트 목록 · 상세 · 삭제(API-REPORT-001~003, S15P31A306-404). 가이드 실행 → 완료 API 로 실제 완료 기록을 만들어 확인한다. 준비
 * 방식은 {@code GuideExecutionApiTest}(서연)와 같다.
 */
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
class HistoryRecordApiTest {
  private static final String EXECUTIONS = "/v1/users/me/executions";
  private static final String RECORDS = "/v1/users/me/history-records";

  @Autowired private WebApplicationContext context;
  @Autowired private SessionRepositoryFilter<?> sessionFilter;
  @Autowired private CookieSerializer cookieSerializer;
  @Autowired private FindByIndexNameSessionRepository<? extends Session> sessions;
  @Autowired private UserRepository users;
  @Autowired private VideoRepository videos;
  @Autowired private FaceRegistrationRepository faces;
  @Autowired private StoredPhotoRepository photos;
  @Autowired private PouchItemRepository pouch;
  @Autowired private GuideMatchGenerationService matching;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private ObjectMapper mapper;
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
    user = users.saveAndFlush(new User(UUID.randomUUID() + "@report.test", "hash")).getId();
    login = login(user);
    video = video();
    guide = guide(video);
    jdbc.update(
        "insert into product_categories values ('LIP', '립', true, true, 1) on conflict do nothing");
    jdbc.update(
        "insert into product_types values ('LIP_TINT', 'LIP', '틴트', 2) on conflict do nothing");
  }

  @Test
  void listShowsMyReportsNewestFirstWithTheCompletedPhoto() throws Exception {
    Completed withPhoto = complete(true);
    Completed withoutPhoto = complete(false);

    mvc.perform(get(RECORDS).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(2))
        .andExpect(jsonPath("$.hasNext").value(false))
        .andExpect(jsonPath("$.items[0].recordId").value(withoutPhoto.recordId().toString()))
        .andExpect(jsonPath("$.items[0].completedPhoto").doesNotExist())
        .andExpect(jsonPath("$.items[1].recordId").value(withPhoto.recordId().toString()))
        .andExpect(jsonPath("$.items[1].guideId").value(guide.toString()))
        .andExpect(jsonPath("$.items[1].videoId").value(video.toString()))
        .andExpect(jsonPath("$.items[1].videoTitle").value("영상"))
        .andExpect(jsonPath("$.items[1].stepCount").isNumber())
        .andExpect(
            jsonPath("$.items[1].completedPhoto.photoId").value(withPhoto.stepPhoto().toString()))
        .andExpect(
            jsonPath("$.items[1].completedPhoto.url")
                .value("/api/v1/users/me/photos/" + withPhoto.stepPhoto()));

    // 완료 시각이 같으면 리포트 ID 내림차순
    jdbc.update(
        "update history_records set completed_at = ? where user_id = ?",
        java.sql.Timestamp.from(Instant.parse("2026-11-11T00:00:00Z")),
        user);
    String larger =
        withPhoto.recordId().toString().compareTo(withoutPhoto.recordId().toString()) > 0
            ? withPhoto.recordId().toString()
            : withoutPhoto.recordId().toString();
    mvc.perform(get(RECORDS).param("size", "1").cookie(login.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].recordId").value(larger))
        .andExpect(jsonPath("$.hasNext").value(true));

    // 다른 회원에게는 보이지 않는다
    Login other =
        login(users.saveAndFlush(new User(UUID.randomUUID() + "@report.test", "hash")).getId());
    mvc.perform(get(RECORDS).cookie(other.cookie()).secure(true))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(0));
  }

  @Test
  void detailReturnsTheSnapshotFixedAtCompletion() throws Exception {
    Completed done = complete(true);
    String saved =
        jdbc.queryForObject(
            "select record_snapshot::text from history_records where id = ?",
            String.class,
            done.recordId());

    MvcResult result =
        mvc.perform(get(RECORDS + "/" + done.recordId()).cookie(login.cookie()).secure(true))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.recordId").value(done.recordId().toString()))
            .andReturn();
    assertThat(mapper.readTree(result.getResponse().getContentAsString()))
        .isEqualTo(mapper.readTree(saved));

    Login other =
        login(users.saveAndFlush(new User(UUID.randomUUID() + "@report.test", "hash")).getId());
    mvc.perform(get(RECORDS + "/" + done.recordId()).cookie(other.cookie()).secure(true))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
    mvc.perform(get(RECORDS + "/" + UUID.randomUUID()).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
  }

  @Test
  void deleteRemovesThePhotoFilesThenTheReport() throws Exception {
    Completed done = complete(true);
    String stepKey = storageKey(done.stepPhoto());
    String faceKey = storageKey(done.facePhoto());

    Login other =
        login(users.saveAndFlush(new User(UUID.randomUUID() + "@report.test", "hash")).getId());
    mvc.perform(
            delete(RECORDS + "/" + done.recordId())
                .cookie(other.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isNotFound());

    mvc.perform(
            delete(RECORDS + "/" + done.recordId())
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isNoContent());

    verify(storage).delete(stepKey);
    verify(storage).delete(faceKey);
    assertThat(photoState(done.stepPhoto())).isEqualTo("DELETED");
    assertThat(photoState(done.facePhoto())).isEqualTo("DELETED");
    mvc.perform(get(RECORDS + "/" + done.recordId()).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
    mvc.perform(
            delete(RECORDS + "/" + done.recordId())
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isNotFound());
    mvc.perform(get(RECORDS).cookie(login.cookie()).secure(true))
        .andExpect(jsonPath("$.items.length()").value(0));
  }

  @Test
  void aStorageFailureIs503AndARetryFinishesTheDeletion() throws Exception {
    Completed done = complete(true);
    String faceKey = storageKey(done.facePhoto());
    doThrow(new StorageException("temporary delete failure", null))
        .when(storage)
        .delete(eq(faceKey));

    mvc.perform(
            delete(RECORDS + "/" + done.recordId())
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("REPORT_DELETE_FAILED"));
    // 리포트는 남고, 못 지운 사진은 정리 대기라 읽을 수 없다
    mvc.perform(get(RECORDS + "/" + done.recordId()).cookie(login.cookie()).secure(true))
        .andExpect(status().isOk());
    assertThat(photoState(done.facePhoto())).isEqualTo("CLEANUP_PENDING");
    assertThat(photoState(done.stepPhoto())).isEqualTo("DELETED");
    mvc.perform(get(RECORDS).cookie(login.cookie()).secure(true))
        .andExpect(jsonPath("$.items[0].completedPhoto").doesNotExist());

    // 저장소가 돌아오고 재시도 시각이 지나면 다시 요청해 남은 것을 지운다
    doNothing().when(storage).delete(eq(faceKey));
    jdbc.update(
        "update photos set next_cleanup_at = now() - interval '1 second' where id = ?",
        done.facePhoto());
    mvc.perform(
            delete(RECORDS + "/" + done.recordId())
                .cookie(login.cookie())
                .secure(true)
                .with(csrf()))
        .andExpect(status().isNoContent());
    assertThat(photoState(done.facePhoto())).isEqualTo("DELETED");
    mvc.perform(get(RECORDS + "/" + done.recordId()).cookie(login.cookie()).secure(true))
        .andExpect(status().isNotFound());
  }

  @Test
  void needsLoginAndCsrf() throws Exception {
    mvc.perform(get(RECORDS).secure(true)).andExpect(status().isUnauthorized());
    mvc.perform(delete(RECORDS + "/" + UUID.randomUUID()).cookie(login.cookie()).secure(true))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
  }

  // ---------- 도움 ----------

  /** 실행을 만들고(사진을 찍으면 동의 · 립 단계 사진) 완료 API 로 리포트를 만든다. */
  private Completed complete(boolean withPhoto) throws Exception {
    UUID item = item().getId();
    UUID face = face();
    UUID facePhoto = faces.findById(face).orElseThrow().getPhotoId();
    UUID match = matching.create(user, new CreateGuideMatchRequest(guide)).matchId();
    MvcResult created =
        mvc.perform(
                post(EXECUTIONS)
                    .cookie(login.cookie())
                    .secure(true)
                    .with(csrf())
                    .contentType("application/json")
                    .content(body(match, face, item).toString()))
            .andExpect(status().isCreated())
            .andReturn();
    String executionId =
        mapper.readTree(created.getResponse().getContentAsString()).path("executionId").asString();
    UUID stepPhoto = null;
    if (withPhoto) {
      mvc.perform(
              patch(EXECUTIONS + "/" + executionId + "/photo-consent")
                  .cookie(login.cookie())
                  .secure(true)
                  .with(csrf())
                  .contentType("application/json")
                  .content("{\"enabled\":true}"))
          .andExpect(status().isOk());
      MvcResult uploaded =
          mvc.perform(
                  multipart(EXECUTIONS + "/" + executionId + "/steps/lip/photo")
                      .file(
                          new MockMultipartFile("image", "capture.png", "image/png", imageBytes()))
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
      stepPhoto =
          UUID.fromString(
              mapper
                  .readTree(uploaded.getResponse().getContentAsString())
                  .path("photoId")
                  .asString());
    }
    MvcResult completion =
        mvc.perform(
                post(EXECUTIONS + "/" + executionId + "/completion")
                    .cookie(login.cookie())
                    .secure(true)
                    .with(csrf()))
            .andExpect(status().isCreated())
            .andReturn();
    JsonNode body = mapper.readTree(completion.getResponse().getContentAsString());
    return new Completed(UUID.fromString(body.path("recordId").asString()), stepPhoto, facePhoto);
  }

  private record Completed(UUID recordId, UUID stepPhoto, UUID facePhoto) {}

  private String storageKey(UUID photoId) {
    return jdbc.queryForObject(
        "select storage_key from photos where id = ?", String.class, photoId);
  }

  private String photoState(UUID photoId) {
    return jdbc.queryForObject("select state from photos where id = ?", String.class, photoId);
  }

  private ObjectNode body(UUID match, UUID face, UUID selected) {
    ObjectNode body = mapper.createObjectNode();
    body.put("guideId", guide.toString());
    body.put("matchId", match.toString());
    body.put("faceRegistrationId", face.toString());
    ObjectNode selection = body.putArray("selections").addObject();
    selection.put("stepId", "lip");
    selection.put("selectedPouchItemId", selected.toString());
    body.put("acceptMissingProducts", true);
    return body;
  }

  private PouchItem item() {
    return pouch.saveAndFlush(
        new PouchItem(
            user,
            RegistrationMode.MANUAL,
            null,
            null,
            "LIP",
            "LIP_TINT",
            "브랜드",
            UUID.randomUUID().toString(),
            null,
            PouchColor.userInput("#AA4455")));
  }

  private UUID face() {
    StoredPhoto photo =
        new StoredPhoto(
            user,
            login.id(),
            PhotoKind.FACE_REGISTRATION,
            null,
            "photos/" + UUID.randomUUID(),
            "image/png",
            10,
            2,
            2,
            null);
    photo.markAvailable();
    StoredPhoto saved = photos.saveAndFlush(photo);
    return faces
        .saveAndFlush(
            new FaceRegistration(
                saved,
                video,
                null,
                new FaceChecks(true, true, true, true, false),
                "v1",
                Instant.now()))
        .getId();
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

  private UUID guide(UUID video) {
    UUID job = UUID.randomUUID();
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, attempt, created_at, updated_at) values (?, ?, 'COMPLETED', 'DONE', false, 1, now(), now())",
        job,
        video);
    UUID id = UUID.randomUUID();
    String input =
        "{\"steps\":[{\"stepId\":\"skin\",\"order\":0,\"makeup\":\"other\"},{\"stepId\":\"lip\",\"order\":1,\"makeup\":\"lip\",\"targetColor\":{\"hex\":\"#AA4455\"},\"product\":{\"brand\":\"영상 브랜드\",\"name\":\"영상 제품\"}}]}";
    jdbc.update(
        "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input, created_at, updated_at) values (?, ?, ?, 1, 'APPROVED', ?::jsonb, now(), now())",
        id,
        video,
        job,
        input);
    return id;
  }

  private Login login(UUID owner) {
    return login(sessions, owner);
  }

  private <S extends Session> Login login(
      FindByIndexNameSessionRepository<S> repository, UUID owner) {
    S session = repository.createSession();
    var authentication =
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(owner, owner + "@report.test"),
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
