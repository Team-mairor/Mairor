package com.mairor.backend.common.external.youtube;

import java.net.SocketTimeoutException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * YouTube Data API v3 의 {@code search.list}(CC BY 영상 검색)와 {@code videos.list}(영상 상세)를 부른다.
 *
 * <p>재시도하지 않는다(사용자 요청 안에서 부르므로 실패를 바로 알린다). 키는 쿼리 {@code key}로 싣고 로그 · 예외 메시지에 넣지 않는다.
 */
@Component
public class YouTubeClient {

  /** {@code videos.list}가 한 번에 받는 최대 ID 수. */
  public static final int MAX_IDS_PER_CALL = 50;

  private final YouTubeProperties properties;
  private final RestClient restClient;
  private final ObjectMapper objectMapper;

  @Autowired
  public YouTubeClient(
      YouTubeProperties properties, RestClient.Builder builder, ObjectMapper objectMapper) {
    this(properties, builder.requestFactory(requestFactory(properties)).build(), objectMapper);
  }

  YouTubeClient(YouTubeProperties properties, RestClient restClient, ObjectMapper objectMapper) {
    this.properties = properties;
    this.restClient = restClient;
    this.objectMapper = objectMapper;
  }

  private static JdkClientHttpRequestFactory requestFactory(YouTubeProperties properties) {
    HttpClient httpClient =
        HttpClient.newBuilder().connectTimeout(properties.connectTimeout()).build();
    JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
    factory.setReadTimeout(properties.readTimeout());
    return factory;
  }

  /**
   * CC BY 영상을 관련도순으로 찾는다.
   *
   * @param query 검색어(앞뒤 공백을 지운 값)
   * @param pageToken 다음 페이지 토큰. 첫 페이지는 null
   * @param size 받을 개수(1~50)
   */
  public YouTubeSearchResult search(String query, String pageToken, int size) {
    UriComponentsBuilder uri =
        UriComponentsBuilder.fromUriString(properties.baseUrl() + "/search")
            .queryParam("part", "snippet")
            .queryParam("type", "video")
            .queryParam("videoLicense", YouTubeVideo.CREATIVE_COMMON)
            .queryParam("maxResults", size)
            .queryParam("regionCode", properties.regionCode())
            .queryParam("relevanceLanguage", properties.relevanceLanguage())
            .queryParam("q", query);
    if (pageToken != null && !pageToken.isBlank()) {
      uri.queryParam("pageToken", pageToken);
    }
    JsonNode root = get(uri);
    List<String> ids = new ArrayList<>();
    for (JsonNode item : root.path("items")) {
      String id = item.path("id").path("videoId").asString("");
      if (!id.isEmpty() && !ids.contains(id)) {
        ids.add(id);
      }
    }
    String next = root.path("nextPageToken").asString("");
    return new YouTubeSearchResult(ids, next.isEmpty() ? null : next);
  }

  /**
   * 영상 상세. 없는 · 지운 영상은 결과에서 빠진다. 결과는 받은 ID 순서다.
   *
   * @param youtubeVideoIds 최대 {@link #MAX_IDS_PER_CALL}개
   */
  public List<YouTubeVideo> videos(List<String> youtubeVideoIds) {
    if (youtubeVideoIds.isEmpty()) {
      return List.of();
    }
    if (youtubeVideoIds.size() > MAX_IDS_PER_CALL) {
      throw new IllegalArgumentException("videos.list 는 한 번에 50개까지 받는다.");
    }
    UriComponentsBuilder uri =
        UriComponentsBuilder.fromUriString(properties.baseUrl() + "/videos")
            .queryParam("part", "snippet,contentDetails,status,statistics")
            .queryParam("id", String.join(",", youtubeVideoIds))
            .queryParam("maxResults", youtubeVideoIds.size());
    JsonNode root = get(uri);
    Map<String, YouTubeVideo> byId = new LinkedHashMap<>();
    for (JsonNode item : root.path("items")) {
      YouTubeVideo video = toVideo(item);
      byId.put(video.youtubeVideoId(), video);
    }
    List<YouTubeVideo> ordered = new ArrayList<>();
    for (String id : youtubeVideoIds) {
      YouTubeVideo video = byId.get(id);
      if (video != null) {
        ordered.add(video);
      }
    }
    return ordered;
  }

  private JsonNode get(UriComponentsBuilder uri) {
    if (!properties.configured()) {
      throw new YouTubeException(
          YouTubeException.Kind.NOT_CONFIGURED, "YouTube 키(app.youtube.api-key)가 없습니다.", null);
    }
    URI target = uri.queryParam("key", properties.apiKey()).encode().build().toUri();
    RawResponse response;
    try {
      response =
          restClient
              .get()
              .uri(target)
              .exchange(
                  (req, res) ->
                      new RawResponse(
                          res.getStatusCode().value(),
                          new String(res.getBody().readAllBytes(), StandardCharsets.UTF_8)));
    } catch (RestClientException e) {
      if (isTimeout(e)) {
        throw new YouTubeException(YouTubeException.Kind.TIMEOUT, "YouTube 응답이 늦습니다.", e);
      }
      throw new YouTubeException(YouTubeException.Kind.UNAVAILABLE, "YouTube 에 연결하지 못했습니다.", e);
    }
    JsonNode root = parse(response.body());
    if (response.status() == 200) {
      return root;
    }
    String reason = root.path("error").path("errors").path(0).path("reason").asString("");
    if (response.status() == 403
        && ("quotaExceeded".equals(reason) || "dailyLimitExceeded".equals(reason))) {
      throw new YouTubeException(
          YouTubeException.Kind.QUOTA_EXCEEDED, "YouTube 하루 할당량을 다 썼습니다.", null);
    }
    throw new YouTubeException(
        YouTubeException.Kind.UNAVAILABLE,
        "YouTube 가 요청을 처리하지 못했습니다(HTTP " + response.status() + ", " + reason + ").",
        null);
  }

  private JsonNode parse(String body) {
    try {
      return objectMapper.readTree(body.isBlank() ? "{}" : body);
    } catch (JacksonException e) {
      throw new YouTubeException(YouTubeException.Kind.UNAVAILABLE, "YouTube 응답이 JSON 이 아닙니다.", e);
    }
  }

  private static YouTubeVideo toVideo(JsonNode item) {
    JsonNode snippet = item.path("snippet");
    JsonNode details = item.path("contentDetails");
    JsonNode status = item.path("status");
    String viewCount = item.path("statistics").path("viewCount").asString("");
    return new YouTubeVideo(
        item.path("id").asString(""),
        snippet.path("title").asString(""),
        snippet.path("channelTitle").asString(""),
        snippet.path("description").asString(""),
        durationSeconds(details.path("duration").asString("")),
        thumbnail(snippet.path("thumbnails")),
        viewCount.isEmpty() ? null : Long.valueOf(viewCount),
        instant(snippet.path("publishedAt").asString("")),
        status.path("privacyStatus").asString(""),
        status.path("license").asString(""),
        "ytAgeRestricted".equals(details.path("contentRating").path("ytRating").asString("")),
        snippet.path("liveBroadcastContent").asString("none"));
  }

  /** ISO 8601 길이({@code PT1H2M3S}, {@code P0D}). 읽을 수 없으면 0. */
  static int durationSeconds(String iso) {
    if (iso.isEmpty()) {
      return 0;
    }
    try {
      return (int) Duration.parse(iso).toSeconds();
    } catch (DateTimeParseException e) {
      return 0;
    }
  }

  private static String thumbnail(JsonNode thumbnails) {
    for (String size : List.of("high", "medium", "default")) {
      String url = thumbnails.path(size).path("url").asString("");
      if (!url.isEmpty()) {
        return url;
      }
    }
    return null;
  }

  private static Instant instant(String value) {
    if (value.isEmpty()) {
      return null;
    }
    try {
      return Instant.parse(value);
    } catch (DateTimeParseException e) {
      return null;
    }
  }

  private static boolean isTimeout(Throwable e) {
    for (Throwable t = e; t != null; t = t.getCause()) {
      if (t instanceof HttpTimeoutException || t instanceof SocketTimeoutException) {
        return true;
      }
    }
    return false;
  }

  private record RawResponse(int status, String body) {}
}
