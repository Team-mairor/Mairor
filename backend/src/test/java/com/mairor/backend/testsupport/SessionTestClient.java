package com.mairor.backend.testsupport;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Map;

/**
 * 실제 HTTP 로 서버를 호출하는 테스트 클라이언트. 쿠키 저장소를 쓰지 않고 응답의 {@code Set-Cookie} 를 그대로 돌려준다. {@code
 * RANDOM_PORT} 의 기본 HTTP 서버에서는 일반 쿠키 저장소가 {@code Secure} 쿠키를 다시 보내지 않을 수 있어서, 테스트가 쿠키 값을 꺼내 다음 요청에
 * 직접 실어 보낸다. 운영의 {@code Secure} 설정은 끄지 않는다.
 */
public class SessionTestClient {

  public static final String SESSION_COOKIE = "__Host-sessionId";

  private final int port;
  private final HttpClient http = HttpClient.newHttpClient();

  public SessionTestClient(int port) {
    this.port = port;
  }

  /**
   * @param jsonBody 요청 본문(JSON). 없으면 {@code null}
   * @param sessionCookie 보낼 세션 쿠키 값({@code Set-Cookie} 에 있던 값 그대로). 없으면 {@code null}
   * @param headers 추가 헤더. 없으면 {@code null}
   */
  public Response call(
      String method,
      String path,
      String jsonBody,
      String sessionCookie,
      Map<String, String> headers)
      throws IOException, InterruptedException {
    HttpRequest.BodyPublisher body =
        jsonBody == null
            ? HttpRequest.BodyPublishers.noBody()
            : HttpRequest.BodyPublishers.ofString(jsonBody);
    HttpRequest.Builder request =
        HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api" + path))
            .method(method, body);
    if (jsonBody != null) {
      request.header("Content-Type", "application/json");
    }
    if (sessionCookie != null) {
      request.header("Cookie", SESSION_COOKIE + "=" + sessionCookie);
    }
    if (headers != null) {
      headers.forEach(request::header);
    }
    HttpResponse<String> response =
        http.send(request.build(), HttpResponse.BodyHandlers.ofString());
    return new Response(
        response.statusCode(),
        response.body(),
        response.headers().allValues("Set-Cookie"),
        response.headers().map());
  }

  public Response call(
      String method, String path, String sessionCookie, Map<String, String> headers)
      throws IOException, InterruptedException {
    return call(method, path, null, sessionCookie, headers);
  }

  public Response get(String path, String sessionCookie) throws IOException, InterruptedException {
    return call("GET", path, null, sessionCookie, null);
  }

  public Response get(String path, String sessionCookie, Map<String, String> headers)
      throws IOException, InterruptedException {
    return call("GET", path, null, sessionCookie, headers);
  }

  public Response post(String path, String sessionCookie) throws IOException, InterruptedException {
    return call("POST", path, null, sessionCookie, null);
  }

  public Response postJson(
      String path, String jsonBody, String sessionCookie, Map<String, String> headers)
      throws IOException, InterruptedException {
    return call("POST", path, jsonBody, sessionCookie, headers);
  }

  /**
   * 응답. {@code setCookies} 는 {@code Set-Cookie} 헤더 값 전체를 응답에 나온 순서대로 담는다. {@code headers} 는 헤더
   * 이름(소문자)별 값이다.
   */
  public record Response(
      int status, String body, List<String> setCookies, Map<String, List<String>> headers) {

    /** 헤더의 첫 값. 없으면 {@code null}. */
    public String header(String name) {
      List<String> values = headers.get(name.toLowerCase(java.util.Locale.ROOT));
      return values == null || values.isEmpty() ? null : values.get(0);
    }

    /** 마지막 세션 쿠키의 값. 세션 쿠키가 없으면 {@code null}. */
    public String sessionCookieValue() {
      String prefix = SESSION_COOKIE + "=";
      for (int i = setCookies.size() - 1; i >= 0; i--) {
        String setCookie = setCookies.get(i);
        if (setCookie.startsWith(prefix)) {
          String value = setCookie.substring(prefix.length());
          int end = value.indexOf(';');
          return end < 0 ? value : value.substring(0, end);
        }
      }
      return null;
    }

    /** 마지막 세션 쿠키의 {@code Set-Cookie} 헤더 전체. 없으면 {@code null}. */
    public String sessionSetCookie() {
      String prefix = SESSION_COOKIE + "=";
      for (int i = setCookies.size() - 1; i >= 0; i--) {
        if (setCookies.get(i).startsWith(prefix)) {
          return setCookies.get(i);
        }
      }
      return null;
    }

    /** 마지막 세션 쿠키의 {@code Max-Age}(초). 세션 쿠키가 없거나 {@code Max-Age} 가 없으면 {@code null}. */
    public Long sessionCookieMaxAge() {
      String setCookie = sessionSetCookie();
      if (setCookie == null) {
        return null;
      }
      for (String attribute : setCookie.split(";")) {
        String trimmed = attribute.trim();
        if (trimmed.regionMatches(true, 0, "Max-Age=", 0, "Max-Age=".length())) {
          return Long.parseLong(trimmed.substring("Max-Age=".length()));
        }
      }
      return null;
    }

    /** 세션 쿠키 {@code Set-Cookie} 헤더 개수. */
    public long sessionCookieCount() {
      return setCookies.stream().filter(c -> c.startsWith(SESSION_COOKIE + "=")).count();
    }
  }
}
