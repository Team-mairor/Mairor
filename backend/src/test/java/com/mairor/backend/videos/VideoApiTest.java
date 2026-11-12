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
import com.mairor.backend.videos.service.PopularVideoService;
import java.sql.Timestamp;
import java.time.Duration;
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

/**
 * 영상 검색 · 선택 · 인기 Top 4 API: 명세 칸, CC BY · 분석 가능 거르기, 가이드 · 내 작업 상태, 선택 기록 · 인기 순위, 오류 코드를
 * PostgreSQL 로 확인한다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@AutoConfigureMockMvc
class VideoApiTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private PopularVideoService popular;
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
    when(youTube.search(eq("메이크업 " + query), isNull(), eq(20)))
        .thenReturn(new YouTubeSearchResult(List.of(), null));

    for (int i = 0; i < 2; i++) {
      mockMvc
          .perform(get("/v1/videos/search").param("q", query).with(asMember(userId)))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.items.length()").value(0))
          .andExpect(jsonPath("$.nextPageToken").doesNotExist());
    }
    verify(youTube, times(1)).search(eq("메이크업 " + query), isNull(), eq(20));
  }

  /** 메이크업이 아닌 영상이 덜 섞이게 검색어 앞에 "메이크업"을 붙인다(S15P31A306-409). 이미 있으면 그대로. */
  @Test
  void searchPutsTheMakeupWordInFrontOnlyWhenItIsMissing() throws Exception {
    when(youTube.search(any(), any(), anyInt()))
        .thenReturn(new YouTubeSearchResult(List.of(), null));

    for (String q : List.of("브이로그 " + prefix, "Make-Up 데일리 " + prefix, "가을 메이크업 " + prefix)) {
      mockMvc
          .perform(get("/v1/videos/search").param("q", q).with(asMember(userId)))
          .andExpect(status().isOk());
    }

    verify(youTube).search(eq("메이크업 브이로그 " + prefix), isNull(), eq(20));
    verify(youTube).search(eq("Make-Up 데일리 " + prefix), isNull(), eq(20));
    verify(youTube).search(eq("가을 메이크업 " + prefix), isNull(), eq(20));
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
    when(youTube.search(eq("메이크업 느림 " + prefix), any(), anyInt()))
        .thenThrow(new YouTubeException(YouTubeException.Kind.TIMEOUT, "slow", null));
    when(youTube.search(eq("메이크업 오류 " + prefix), any(), anyInt()))
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
    // 성공한 선택마다 선택 기록이 한 줄씩 남는다(인기 Top 4 를 센다)
    assertThat(selectionsOf(userId)).isEqualTo(2);
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
    assertThat(selectionsOf(userId)).isZero();
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

  // ---------- 인기 Top 4 ----------

  @Test
  void popularRanksByDistinctMembersWithinThirtyDays() throws Exception {
    resetPopular();
    List<UUID> members = List.of(userId, otherUserId, insertUser(), insertUser(), insertUser());
    Instant now = Instant.now();
    UUID most = insertVideo(yt("p_a"));
    UUID repeated = insertVideo(yt("p_b"));
    UUID tiedEarlier = insertVideo(yt("p_c"));
    UUID tiedLater = insertVideo(yt("p_d"));
    UUID single = insertVideo(yt("p_e"));
    UUID mostlyOld = insertVideo(yt("p_f"));
    UUID guideId = insertApprovedGuide(most);
    insertGuide(tiedEarlier, "REJECTED");

    for (int i = 0; i < 3; i++) {
      insertSelection(most, members.get(i), now.minus(Duration.ofDays(1)));
    }
    // 같은 회원이 여러 번 골라도 1 이다
    for (int i = 0; i < 5; i++) {
      insertSelection(repeated, userId, now.minus(Duration.ofHours(3 + i)));
    }
    // 회원 수가 같으면 마지막 선택이 늦은 영상이 앞이다
    insertSelection(tiedEarlier, members.get(0), now.minus(Duration.ofHours(5)));
    insertSelection(tiedEarlier, members.get(1), now.minus(Duration.ofHours(2)));
    insertSelection(tiedLater, members.get(2), now.minus(Duration.ofHours(4)));
    insertSelection(tiedLater, members.get(3), now.minus(Duration.ofHours(1)));
    insertSelection(single, members.get(4), now.minus(Duration.ofMinutes(10)));
    // 30일이 지난 선택은 세지 않는다
    for (int i = 0; i < 4; i++) {
      insertSelection(mostlyOld, members.get(i), now.minus(Duration.ofDays(31)));
    }
    insertSelection(mostlyOld, members.get(4), now.minus(Duration.ofHours(6)));

    String body =
        mockMvc
            .perform(get("/v1/videos/popular").with(asMember(userId)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(4))
            .andExpect(jsonPath("$.items[0].rank").value(1))
            .andExpect(jsonPath("$.items[0].youtubeVideoId").value(yt("p_a")))
            .andExpect(jsonPath("$.items[0].videoId").value(most.toString()))
            .andExpect(jsonPath("$.items[0].guideId").value(guideId.toString()))
            .andExpect(jsonPath("$.items[0].guideAvailable").value(true))
            .andExpect(jsonPath("$.items[0].title").value("저장된 제목"))
            .andExpect(jsonPath("$.items[0].channelTitle").value("채널"))
            .andExpect(jsonPath("$.items[0].durationSeconds").value(600))
            .andExpect(jsonPath("$.items[0].viewCount").doesNotExist())
            .andExpect(jsonPath("$.items[1].rank").value(2))
            .andExpect(jsonPath("$.items[1].youtubeVideoId").value(yt("p_d")))
            .andExpect(jsonPath("$.items[1].videoId").value(tiedLater.toString()))
            .andExpect(jsonPath("$.items[2].rank").value(3))
            .andExpect(jsonPath("$.items[2].youtubeVideoId").value(yt("p_c")))
            // 반려된 가이드는 붙이지 않는다
            .andExpect(jsonPath("$.items[2].guideId").doesNotExist())
            .andExpect(jsonPath("$.items[2].guideAvailable").value(false))
            .andExpect(jsonPath("$.items[3].rank").value(4))
            .andExpect(jsonPath("$.items[3].youtubeVideoId").value(yt("p_e")))
            .andExpect(jsonPath("$.rankingBasis").value("DISTINCT_MEMBER_SELECTIONS"))
            .andExpect(jsonPath("$.aggregationScope").value("LAST_30_DAYS"))
            .andReturn()
            .getResponse()
            .getContentAsString();
    // 한 회원이 다섯 번 고른 영상 · 30일 지난 선택이 대부분인 영상은 회원 1명이라 4위 밖이다
    assertThat(body).doesNotContain(yt("p_b"), yt("p_f"));
  }

  @Test
  void popularReturnsFewerThanFourAndKeepsTheCountUntilTheNextRefresh() throws Exception {
    resetPopular();
    String selected = yt("p_s");
    when(youTube.videos(List.of(selected))).thenReturn(List.of(cc(selected)));
    mockMvc.perform(select(selected).with(asMember(userId))).andExpect(status().isOk());
    insertSelection(insertVideo(yt("p_t")), otherUserId, Instant.now().minus(Duration.ofDays(2)));

    String body =
        mockMvc
            .perform(get("/v1/videos/popular").with(asMember(userId)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andExpect(jsonPath("$.items[0].youtubeVideoId").value(selected))
            .andExpect(jsonPath("$.items[0].thumbnailUrl").value(cc(selected).thumbnailUrl()))
            .andExpect(jsonPath("$.items[0].publishedAt").value("2026-10-01T09:00:00Z"))
            .andExpect(jsonPath("$.items[1].youtubeVideoId").value(yt("p_t")))
            .andReturn()
            .getResponse()
            .getContentAsString();
    String updatedAt = jsonField(body, "updatedAt");
    Instant nextRefreshAt = Instant.parse(jsonField(body, "nextRefreshAt"));
    assertThat(Duration.between(Instant.parse(updatedAt), nextRefreshAt))
        .isEqualTo(Duration.ofMinutes(10));

    // 다시 셀 때까지는 담아 둔 결과를 준다
    insertSelection(insertVideo(yt("p_u")), userId, Instant.now());
    mockMvc
        .perform(get("/v1/videos/popular").with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(2))
        .andExpect(jsonPath("$.updatedAt").value(updatedAt));

    popular.expire();
    mockMvc
        .perform(get("/v1/videos/popular").with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(3))
        .andExpect(jsonPath("$.items[0].youtubeVideoId").value(yt("p_u")));
  }

  @Test
  void popularWithoutRecentSelectionsIsServiceUnavailable() throws Exception {
    resetPopular();
    insertSelection(insertVideo(yt("p_o")), userId, Instant.now().minus(Duration.ofDays(31)));

    mockMvc
        .perform(get("/v1/videos/popular").with(asMember(userId)))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("VIDEO_POPULAR_UNAVAILABLE"));

    // 빈 결과는 담아 두지 않아, 첫 선택이 생기면 다시 셀 시각을 기다리지 않고 바로 보인다
    insertSelection(insertVideo(yt("p_n")), otherUserId, Instant.now());
    mockMvc
        .perform(get("/v1/videos/popular").with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].youtubeVideoId").value(yt("p_n")));
  }

  @Test
  void popularNeedsLogin() throws Exception {
    mockMvc.perform(get("/v1/videos/popular")).andExpect(status().isUnauthorized());
  }

  // ---------- 도움 ----------

  private static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder select(
      String youtubeVideoId) {
    return post("/v1/videos")
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"youtubeVideoId\": \"" + youtubeVideoId + "\"}");
  }

  /** 다른 테스트의 선택 기록을 지우고 담아 둔 인기 결과를 버린다. 인기 순위는 모든 회원의 선택을 센다. */
  private void resetPopular() {
    jdbc.update("delete from video_selections");
    popular.expire();
  }

  private UUID insertUser() {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
        id,
        id + "@example.com");
    return id;
  }

  private void insertSelection(UUID videoId, UUID memberId, Instant selectedAt) {
    jdbc.update(
        "insert into video_selections (id, video_id, user_id, selected_at) values (?, ?, ?, ?)",
        UUID.randomUUID(),
        videoId,
        memberId,
        Timestamp.from(selectedAt));
  }

  private int selectionsOf(UUID memberId) {
    return jdbc.queryForObject(
        "select count(*) from video_selections where user_id = ?", Integer.class, memberId);
  }

  private static String jsonField(String body, String field) {
    String key = "\"" + field + "\":\"";
    int start = body.indexOf(key) + key.length();
    return body.substring(start, body.indexOf('"', start));
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
    return insertGuide(videoId, "APPROVED");
  }

  private UUID insertGuide(UUID videoId, String reviewStatus) {
    UUID jobId = insertJob(videoId, null, "COMPLETED");
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input,"
            + " created_at, updated_at) values (?, ?, ?, 1, ?, '{}'::jsonb, now(), now())",
        id,
        videoId,
        jobId,
        reviewStatus);
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
