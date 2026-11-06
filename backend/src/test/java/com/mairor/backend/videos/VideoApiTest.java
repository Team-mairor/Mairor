package com.mairor.backend.videos;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.external.youtube.YouTubeClient;
import com.mairor.backend.common.external.youtube.YouTubeException;
import com.mairor.backend.common.external.youtube.YouTubeSearchResult;
import com.mairor.backend.common.external.youtube.YouTubeVideo;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

/** 영상 검색 · 선택 API: 명세 칸, CC BY · 분석 가능 거르기, 가이드 · 내 작업 상태, 오류 코드를 PostgreSQL 로 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@AutoConfigureMockMvc
class VideoApiTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;
  @MockitoBean private YouTubeClient youTube;

  private UUID userId;
  private UUID otherUserId;
  private String prefix;

  @BeforeEach
  void setUp() {
    userId = UUID.randomUUID();
    otherUserId = UUID.randomUUID();
    for (UUID id : List.of(userId, otherUserId)) {
      jdbc.update(
          "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
          id,
          id + "@example.com");
    }
    // 테스트마다 다른 영상 ID 를 써서 서로 섞이지 않게 한다(11자)
    prefix = UUID.randomUUID().toString().replace("-", "").substring(0, 8);
  }

  private String yt(String suffix) {
    return prefix + suffix;
  }

  private static YouTubeVideo video(
      String id, String license, String privacy, boolean ageRestricted, String description) {
    return new YouTubeVideo(
        id,
        "제목 " + id,
        "채널",
        description,
        600,
        "https://i.ytimg.com/vi/" + id + "/hqdefault.jpg",
        1000L,
        Instant.parse("2026-10-01T09:00:00Z"),
        privacy,
        license,
        ageRestricted,
        "none");
  }

  private static YouTubeVideo cc(String id) {
    return video(id, "creativeCommon", "public", false, "");
  }

  // ---------- 검색 ----------

  @Test
  void searchReturnsAnalyzableVideosWithGuideStatus() throws Exception {
    String approvedId = yt("aaa");
    String plainId = yt("bbb");
    String ageId = yt("ccc");
    UUID videoId = insertVideo(approvedId);
    UUID guideId = insertApprovedGuide(videoId);
    when(youTube.search(eq("데일리 메이크업"), isNull(), eq(3)))
        .thenReturn(new YouTubeSearchResult(List.of(approvedId, plainId, ageId), "NEXT"));
    when(youTube.videos(List.of(approvedId, plainId, ageId)))
        .thenReturn(
            List.of(
                cc(approvedId), cc(plainId), video(ageId, "creativeCommon", "public", true, "")));

    mockMvc
        .perform(
            get("/v1/videos/search")
                .param("q", "  데일리 메이크업 ")
                .param("size", "3")
                .with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.size").value(3))
        .andExpect(jsonPath("$.nextPageToken").value("NEXT"))
        .andExpect(jsonPath("$.items.length()").value(2))
        .andExpect(jsonPath("$.items[0].youtubeVideoId").value(approvedId))
        .andExpect(jsonPath("$.items[0].guideAvailable").value(true))
        .andExpect(jsonPath("$.items[0].guideId").value(guideId.toString()))
        .andExpect(jsonPath("$.items[0].durationSeconds").value(600))
        .andExpect(jsonPath("$.items[0].viewCount").value(1000))
        .andExpect(jsonPath("$.items[0].publishedAt").value("2026-10-01T09:00:00Z"))
        .andExpect(jsonPath("$.items[1].youtubeVideoId").value(plainId))
        .andExpect(jsonPath("$.items[1].guideAvailable").value(false))
        .andExpect(jsonPath("$.items[1].guideId").doesNotExist());
  }

  @Test
  void sameSearchIsCached() throws Exception {
    String query = "캐시 " + prefix;
    when(youTube.search(eq(query), isNull(), eq(20)))
        .thenReturn(new YouTubeSearchResult(List.of(), null));

    for (int i = 0; i < 2; i++) {
      mockMvc
          .perform(get("/v1/videos/search").param("q", query).with(asMember(userId)))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.items.length()").value(0))
          .andExpect(jsonPath("$.nextPageToken").doesNotExist());
    }
    verify(youTube, times(1)).search(eq(query), isNull(), eq(20));
  }

  @Test
  void searchValidatesQueryAndSize() throws Exception {
    mockMvc
        .perform(get("/v1/videos/search").param("q", "   ").with(asMember(userId)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("q"));
    mockMvc
        .perform(
            get("/v1/videos/search").param("q", "립").param("size", "51").with(asMember(userId)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("size"));
  }

  @Test
  void searchQuotaExceededIsServiceUnavailable() throws Exception {
    when(youTube.search(any(), any(), anyInt()))
        .thenThrow(new YouTubeException(YouTubeException.Kind.QUOTA_EXCEEDED, "quota", null));

    mockMvc
        .perform(get("/v1/videos/search").param("q", "할당량 " + prefix).with(asMember(userId)))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("VIDEO_SEARCH_UNAVAILABLE"));
  }

  @Test
  void searchTimeoutAndProviderError() throws Exception {
    when(youTube.search(eq("느림 " + prefix), any(), anyInt()))
        .thenThrow(new YouTubeException(YouTubeException.Kind.TIMEOUT, "slow", null));
    when(youTube.search(eq("오류 " + prefix), any(), anyInt()))
        .thenThrow(new YouTubeException(YouTubeException.Kind.UNAVAILABLE, "down", null));

    mockMvc
        .perform(get("/v1/videos/search").param("q", "느림 " + prefix).with(asMember(userId)))
        .andExpect(status().isGatewayTimeout())
        .andExpect(jsonPath("$.code").value("VIDEO_PROVIDER_TIMEOUT"));
    mockMvc
        .perform(get("/v1/videos/search").param("q", "오류 " + prefix).with(asMember(userId)))
        .andExpect(status().isBadGateway())
        .andExpect(jsonPath("$.code").value("VIDEO_PROVIDER_ERROR"));
  }

  @Test
  void searchNeedsLogin() throws Exception {
    mockMvc
        .perform(get("/v1/videos/search").param("q", "립"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
  }

  // ---------- 선택 ----------

  @Test
  void selectSavesVideoWithChaptersAndUpdatesOnSecondCall() throws Exception {
    String id = yt("sel");
    when(youTube.videos(List.of(id)))
        .thenReturn(
            List.of(video(id, "creativeCommon", "public", false, "0:00 인트로\n1:00 베이스\n2:30 립")));

    String first =
        mockMvc
            .perform(select(id).with(asMember(userId)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.youtubeVideoId").value(id))
            .andExpect(jsonPath("$.chapters.length()").value(3))
            .andExpect(jsonPath("$.chapters[2].startSeconds").value(150))
            .andExpect(jsonPath("$.chapters[2].label").value("립"))
            .andExpect(jsonPath("$.guideAvailable").value(false))
            .andExpect(jsonPath("$.guideId").doesNotExist())
            .andExpect(jsonPath("$.analysisJobId").doesNotExist())
            .andExpect(jsonPath("$.reviewStatus").doesNotExist())
            .andReturn()
            .getResponse()
            .getContentAsString();

    when(youTube.videos(List.of(id)))
        .thenReturn(
            List.of(
                new YouTubeVideo(
                    id,
                    "바뀐 제목",
                    "채널",
                    "",
                    600,
                    null,
                    null,
                    null,
                    "public",
                    "creativeCommon",
                    false,
                    "none")));
    mockMvc
        .perform(select(id).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.title").value("바뀐 제목"))
        .andExpect(jsonPath("$.chapters.length()").value(0));

    Integer rows =
        jdbc.queryForObject(
            "select count(*) from videos where youtube_video_id = ?", Integer.class, id);
    String title =
        jdbc.queryForObject(
            "select title from videos where youtube_video_id = ?", String.class, id);
    assertThat(rows).isEqualTo(1);
    assertThat(title).isEqualTo("바뀐 제목");
    assertThat(first).contains("\"videoId\"");
  }

  @Test
  void selectShowsOnlyMyActiveJobAndApprovedGuide() throws Exception {
    String mine = yt("min");
    String others = yt("oth");
    UUID mineVideo = insertVideo(mine);
    UUID othersVideo = insertVideo(others);
    UUID myJob = insertJob(mineVideo, userId, "RUNNING");
    insertJob(othersVideo, otherUserId, "RUNNING");
    when(youTube.videos(anyList()))
        .thenAnswer(inv -> List.of(cc(((List<String>) inv.getArgument(0)).getFirst())));

    mockMvc
        .perform(select(mine).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.videoId").value(mineVideo.toString()))
        .andExpect(jsonPath("$.analysisJobId").value(myJob.toString()))
        .andExpect(jsonPath("$.reviewStatus").value("NOT_READY"));
    mockMvc
        .perform(select(others).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.analysisJobId").doesNotExist())
        .andExpect(jsonPath("$.reviewStatus").value("NOT_READY"));

    String approved = yt("apr");
    UUID approvedVideo = insertVideo(approved);
    UUID guideId = insertApprovedGuide(approvedVideo);
    mockMvc
        .perform(select(approved).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.guideAvailable").value(true))
        .andExpect(jsonPath("$.guideId").value(guideId.toString()))
        .andExpect(jsonPath("$.reviewStatus").value("APPROVED"));
  }

  @Test
  void selectRejectsUnsupportedVideos() throws Exception {
    String standard = yt("std");
    String privateId = yt("prv");
    String ageId = yt("age");
    when(youTube.videos(List.of(standard)))
        .thenReturn(List.of(video(standard, "youtube", "public", false, "")));
    when(youTube.videos(List.of(privateId)))
        .thenReturn(List.of(video(privateId, "creativeCommon", "unlisted", false, "")));
    when(youTube.videos(List.of(ageId)))
        .thenReturn(List.of(video(ageId, "creativeCommon", "public", true, "")));

    for (String id : List.of(standard, privateId, ageId)) {
      mockMvc
          .perform(select(id).with(asMember(userId)))
          .andExpect(status().isConflict())
          .andExpect(jsonPath("$.code").value("VIDEO_UNSUPPORTED_FOR_ANALYSIS"));
    }
    Integer rows =
        jdbc.queryForObject(
            "select count(*) from videos where youtube_video_id in (?, ?, ?)",
            Integer.class,
            standard,
            privateId,
            ageId);
    assertThat(rows).isZero();
  }

  @Test
  void selectErrors() throws Exception {
    mockMvc
        .perform(select("short").with(asMember(userId)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("youtubeVideoId"));

    String missing = yt("mis");
    when(youTube.videos(List.of(missing))).thenReturn(List.of());
    mockMvc
        .perform(select(missing).with(asMember(userId)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("VIDEO_UNSUPPORTED_FOR_ANALYSIS"));

    String quota = yt("quo");
    when(youTube.videos(List.of(quota)))
        .thenThrow(new YouTubeException(YouTubeException.Kind.QUOTA_EXCEEDED, "quota", null));
    mockMvc
        .perform(select(quota).with(asMember(userId)))
        .andExpect(status().isBadGateway())
        .andExpect(jsonPath("$.code").value("VIDEO_PROVIDER_ERROR"));
  }

  @Test
  void selectNeedsLoginAndCsrf() throws Exception {
    mockMvc.perform(select(yt("csr"))).andExpect(status().isUnauthorized());
    mockMvc
        .perform(
            post("/v1/videos")
                .with(asMember(userId))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"youtubeVideoId\": \"" + yt("csr") + "\"}"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
  }

  @Test
  void activeReanalysisShowsNotReadyOverRejectedGuide() throws Exception {
    String id = yt("rej");
    UUID videoId = insertVideo(id);
    UUID oldJob = insertJob(videoId, null, "COMPLETED");
    jdbc.update(
        "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input,"
            + " created_at, updated_at) values (?, ?, ?, 1, 'REJECTED', '{}'::jsonb, now(), now())",
        UUID.randomUUID(),
        videoId,
        oldJob);
    when(youTube.videos(List.of(id))).thenReturn(List.of(cc(id)));

    mockMvc
        .perform(select(id).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.reviewStatus").value("REJECTED"));

    insertJob(videoId, userId, "PENDING");
    mockMvc
        .perform(select(id).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.reviewStatus").value("NOT_READY"))
        .andExpect(jsonPath("$.guideAvailable").value(false));
  }

  // ---------- 도움 ----------

  private static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder select(
      String youtubeVideoId) {
    return post("/v1/videos")
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"youtubeVideoId\": \"" + youtubeVideoId + "\"}");
  }

  private UUID insertVideo(String youtubeVideoId) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into videos (id, youtube_video_id, title, channel_title, duration_seconds, chapters,"
            + " meta_refreshed_at, created_at, updated_at) values (?, ?, '저장된 제목', '채널', 600, '[]'::jsonb,"
            + " now(), now(), now())",
        id,
        youtubeVideoId);
    return id;
  }

  private UUID insertJob(UUID videoId, UUID requestedBy, String status) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, requested_by, attempt,"
            + " created_at, updated_at) values (?, ?, ?, 'QUEUED', false, ?, 1, now(), now())",
        id,
        videoId,
        status,
        requestedBy);
    return id;
  }

  private UUID insertApprovedGuide(UUID videoId) {
    UUID jobId = insertJob(videoId, null, "COMPLETED");
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input,"
            + " created_at, updated_at) values (?, ?, ?, 1, 'APPROVED', '{}'::jsonb, now(), now())",
        id,
        videoId,
        jobId);
    return id;
  }

  private static RequestPostProcessor asMember(UUID id) {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(id, "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }
}
