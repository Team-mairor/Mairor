package com.mairor.backend.common.external.youtube;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.queryParam;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.io.IOException;
import java.net.SocketTimeoutException;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.hamcrest.Matchers;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.json.JsonMapper;

/** YouTube 호출: 검색 조건(CC BY), 영상 상세 해석, 실패 분류(할당량 · 5xx · 시간 초과 · 키 없음). */
class YouTubeClientTest {

  private static final String BASE = "https://www.googleapis.com/youtube/v3";

  private MockRestServiceServer server;
  private YouTubeClient client;

  @BeforeEach
  void setUp() {
    client = client("test-key");
  }

  private YouTubeClient client(String key) {
    YouTubeProperties properties =
        new YouTubeProperties(
            BASE,
            key,
            Duration.ofSeconds(1),
            Duration.ofSeconds(1),
            "KR",
            "ko",
            Duration.ofMinutes(10),
            100);
    RestClient.Builder builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    return new YouTubeClient(properties, builder.build(), JsonMapper.builder().build());
  }

  @Test
  void searchAsksForCreativeCommonVideosOnly() {
    server
        .expect(requestTo(Matchers.startsWith(BASE + "/search")))
        .andExpect(method(HttpMethod.GET))
        .andExpect(queryParam("videoLicense", "creativeCommon"))
        .andExpect(queryParam("type", "video"))
        .andExpect(queryParam("maxResults", "2"))
        .andExpect(queryParam("pageToken", "NEXT1"))
        .andExpect(queryParam("key", "test-key"))
        .andRespond(
            withSuccess(
                """
                {"nextPageToken": "NEXT2",
                 "items": [{"id": {"videoId": "AAAAAAAAAAA"}}, {"id": {"videoId": "BBBBBBBBBBB"}},
                           {"id": {"kind": "youtube#channel"}}]}
                """,
                MediaType.APPLICATION_JSON));

    YouTubeSearchResult result = client.search("데일리 메이크업", "NEXT1", 2);

    assertThat(result.videoIds()).containsExactly("AAAAAAAAAAA", "BBBBBBBBBBB");
    assertThat(result.nextPageToken()).isEqualTo("NEXT2");
    server.verify();
  }

  @Test
  void videosReadsDetailsInRequestedOrderAndSkipsMissing() {
    server
        .expect(requestTo(Matchers.startsWith(BASE + "/videos")))
        .andExpect(queryParam("part", "snippet,contentDetails,status,statistics"))
        .andRespond(
            withSuccess(
                """
                {"items": [
                  {"id": "BBBBBBBBBBB",
                   "snippet": {"title": "B", "channelTitle": "채널B", "description": "",
                               "publishedAt": "2026-10-01T09:00:00Z", "liveBroadcastContent": "none",
                               "thumbnails": {"default": {"url": "https://i.ytimg.com/b/default.jpg"}}},
                   "contentDetails": {"duration": "PT31M2S", "contentRating": {"ytRating": "ytAgeRestricted"}},
                   "status": {"privacyStatus": "public", "license": "youtube"},
                   "statistics": {}},
                  {"id": "AAAAAAAAAAA",
                   "snippet": {"title": "A", "channelTitle": "채널A", "description": "0:00 시작",
                               "publishedAt": "2026-09-01T00:00:00Z", "liveBroadcastContent": "none",
                               "thumbnails": {"high": {"url": "https://i.ytimg.com/a/high.jpg"},
                                              "default": {"url": "https://i.ytimg.com/a/default.jpg"}}},
                   "contentDetails": {"duration": "PT1H2M3S"},
                   "status": {"privacyStatus": "public", "license": "creativeCommon"},
                   "statistics": {"viewCount": "12345"}}
                ]}
                """,
                MediaType.APPLICATION_JSON));

    List<YouTubeVideo> videos = client.videos(List.of("AAAAAAAAAAA", "ZZZZZZZZZZZ", "BBBBBBBBBBB"));

    assertThat(videos)
        .extracting(YouTubeVideo::youtubeVideoId)
        .containsExactly("AAAAAAAAAAA", "BBBBBBBBBBB");
    YouTubeVideo a = videos.get(0);
    assertThat(a.durationSeconds()).isEqualTo(3723);
    assertThat(a.thumbnailUrl()).isEqualTo("https://i.ytimg.com/a/high.jpg");
    assertThat(a.viewCount()).isEqualTo(12345L);
    assertThat(a.publishedAt()).isEqualTo(Instant.parse("2026-09-01T00:00:00Z"));
    assertThat(a.analyzable()).isTrue();
    YouTubeVideo b = videos.get(1);
    assertThat(b.ageRestricted()).isTrue();
    assertThat(b.creativeCommon()).isFalse();
    assertThat(b.viewCount()).isNull();
    assertThat(b.thumbnailUrl()).isEqualTo("https://i.ytimg.com/b/default.jpg");
    assertThat(b.analyzable()).isFalse();
  }

  @Test
  void emptyIdListDoesNotCallYouTube() {
    assertThat(client.videos(List.of())).isEmpty();
    server.verify();
  }

  @Test
  void quotaExceededIsItsOwnKind() {
    server
        .expect(requestTo(Matchers.startsWith(BASE + "/search")))
        .andRespond(
            withStatus(HttpStatus.FORBIDDEN)
                .contentType(MediaType.APPLICATION_JSON)
                .body(
                    """
                    {"error": {"code": 403, "errors": [{"reason": "quotaExceeded"}]}}
                    """));

    assertThatThrownBy(() -> client.search("립", null, 20))
        .isInstanceOf(YouTubeException.class)
        .extracting(e -> ((YouTubeException) e).kind())
        .isEqualTo(YouTubeException.Kind.QUOTA_EXCEEDED);
  }

  @Test
  void serverErrorIsUnavailable() {
    server
        .expect(requestTo(Matchers.startsWith(BASE + "/videos")))
        .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

    assertThatThrownBy(() -> client.videos(List.of("AAAAAAAAAAA")))
        .isInstanceOf(YouTubeException.class)
        .extracting(e -> ((YouTubeException) e).kind())
        .isEqualTo(YouTubeException.Kind.UNAVAILABLE);
  }

  @Test
  void readTimeoutIsTimeout() {
    server
        .expect(requestTo(Matchers.startsWith(BASE + "/videos")))
        .andRespond(withException(new SocketTimeoutException("read timed out")));

    assertThatThrownBy(() -> client.videos(List.of("AAAAAAAAAAA")))
        .isInstanceOf(YouTubeException.class)
        .extracting(e -> ((YouTubeException) e).kind())
        .isEqualTo(YouTubeException.Kind.TIMEOUT);
  }

  @Test
  void connectionFailureIsUnavailable() {
    server
        .expect(requestTo(Matchers.startsWith(BASE + "/search")))
        .andRespond(withException(new IOException("connection refused")));

    assertThatThrownBy(() -> client.search("립", null, 20))
        .isInstanceOf(YouTubeException.class)
        .extracting(e -> ((YouTubeException) e).kind())
        .isEqualTo(YouTubeException.Kind.UNAVAILABLE);
  }

  @Test
  void missingKeyFailsWithoutCalling() {
    YouTubeClient noKey = client(" ");

    assertThatThrownBy(() -> noKey.search("립", null, 20))
        .isInstanceOf(YouTubeException.class)
        .extracting(e -> ((YouTubeException) e).kind())
        .isEqualTo(YouTubeException.Kind.NOT_CONFIGURED);
    server.verify();
  }

  @Test
  void durationParsing() {
    assertThat(YouTubeClient.durationSeconds("PT45S")).isEqualTo(45);
    assertThat(YouTubeClient.durationSeconds("PT10M")).isEqualTo(600);
    assertThat(YouTubeClient.durationSeconds("P0D")).isZero();
    assertThat(YouTubeClient.durationSeconds("")).isZero();
    assertThat(YouTubeClient.durationSeconds("bad")).isZero();
  }
}
