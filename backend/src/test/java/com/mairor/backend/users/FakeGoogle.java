package com.mairor.backend.users;

import com.mairor.backend.users.support.GoogleClientRegistrations;
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.UnaryOperator;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.config.oauth2.client.CommonOAuth2Provider;

/**
 * 테스트용 가짜 Google. 토큰 주소와 공개키(JWKS) 주소를 JDK 내장 HTTP 서버로 띄우고, 테스트용 RSA 키로 서명한 ID 토큰을 준다. 등록 정보는
 * token·JWKS 주소만 이 서버로 바꾸고 issuer 는 실제 Google 값 그대로라, 서명·iss·aud·exp·nonce 검증을 실제 경로로 확인한다.
 *
 * <p>테스트는 {@link #willIssue} 로 다음 토큰 응답의 클레임을 정하고, {@link Registrations} 를 {@code @Import} 해서 등록
 * 정보를 바꿔 끼운다. 서버는 테스트 JVM 하나에 하나만 뜬다.
 */
public final class FakeGoogle {

  public static final String CLIENT_ID = "test-client";
  public static final String REDIRECT_URI =
      "http://localhost:3000/api/v1/users/oauth/google/callback";

  private static final RSAKey SIGNING_KEY = generateKey("test-key");
  private static final RSAKey OTHER_KEY = generateKey("test-key");
  private static final AtomicReference<TokenResponse> NEXT = new AtomicReference<>();
  private static final HttpServer SERVER = start();

  private FakeGoogle() {}

  /**
   * 다음 토큰 요청에 줄 응답.
   *
   * @param status HTTP 상태. 200 이 아니면 본문 없이 응답한다
   * @param claims ID 토큰 클레임
   * @param signWithOtherKey 공개키에 없는 키로 서명한다 (서명 검증 실패)
   */
  public record TokenResponse(int status, JWTClaimsSet claims, boolean signWithOtherKey) {}

  /** 정상 Google 사용자의 ID 토큰을 만든다. {@code customize} 로 클레임을 바꿀 수 있다. */
  public static void willIssue(
      String subject, String email, String nonce, UnaryOperator<JWTClaimsSet.Builder> customize) {
    Instant now = Instant.now();
    JWTClaimsSet.Builder claims =
        new JWTClaimsSet.Builder()
            .issuer("https://accounts.google.com")
            .audience(CLIENT_ID)
            .subject(subject)
            .issueTime(Date.from(now))
            .expirationTime(Date.from(now.plusSeconds(300)))
            .claim("nonce", nonce)
            .claim("email", email)
            .claim("email_verified", true)
            .claim("name", "Google 사용자");
    NEXT.set(new TokenResponse(200, customize.apply(claims).build(), false));
  }

  public static void willIssue(String subject, String email, String nonce) {
    willIssue(subject, email, nonce, UnaryOperator.identity());
  }

  public static void willRespond(TokenResponse response) {
    NEXT.set(response);
  }

  public static void willSignWithOtherKey(String subject, String email, String nonce) {
    willIssue(subject, email, nonce);
    TokenResponse issued = NEXT.get();
    NEXT.set(new TokenResponse(200, issued.claims(), true));
  }

  public static String baseUrl() {
    return "http://127.0.0.1:" + SERVER.getAddress().getPort();
  }

  /** token·JWKS 주소를 가짜 서버로 바꾼 Google 등록 정보를 앱의 것 대신 쓴다. */
  @TestConfiguration(proxyBeanMethods = false)
  public static class Registrations {
    @Bean
    @Primary
    GoogleClientRegistrations fakeGoogleClientRegistrations() {
      return new GoogleClientRegistrations(
          CommonOAuth2Provider.GOOGLE
              .getBuilder("google")
              .clientId(CLIENT_ID)
              .clientSecret("test-secret")
              .redirectUri(REDIRECT_URI)
              .tokenUri(baseUrl() + "/token")
              .jwkSetUri(baseUrl() + "/jwks")
              .build());
    }
  }

  private static HttpServer start() {
    try {
      HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
      server.createContext("/token", FakeGoogle::token);
      server.createContext(
          "/jwks",
          exchange ->
              respond(exchange, 200, new JWKSet(SIGNING_KEY.toPublicJWK()).toString(false)));
      server.start();
      return server;
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  private static void token(HttpExchange exchange) throws IOException {
    exchange.getRequestBody().readAllBytes();
    TokenResponse next = NEXT.getAndSet(null);
    if (next == null) {
      respond(exchange, 400, "{\"error\":\"invalid_grant\"}");
      return;
    }
    if (next.status() != 200) {
      respond(exchange, next.status(), "");
      return;
    }
    String idToken = sign(next.claims(), next.signWithOtherKey() ? OTHER_KEY : SIGNING_KEY);
    respond(
        exchange,
        200,
        "{\"access_token\":\"fake-access\",\"token_type\":\"Bearer\",\"expires_in\":3600,"
            + "\"scope\":\"openid email profile\",\"id_token\":\""
            + idToken
            + "\"}");
  }

  private static void respond(HttpExchange exchange, int status, String body) throws IOException {
    byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set("Content-Type", "application/json");
    exchange.sendResponseHeaders(status, bytes.length == 0 ? -1 : bytes.length);
    if (bytes.length > 0) {
      exchange.getResponseBody().write(bytes);
    }
    exchange.close();
  }

  private static String sign(JWTClaimsSet claims, RSAKey key) {
    try {
      SignedJWT jwt =
          new SignedJWT(
              new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(key.getKeyID()).build(), claims);
      jwt.sign(new RSASSASigner(key));
      return jwt.serialize();
    } catch (JOSEException e) {
      throw new IllegalStateException(e);
    }
  }

  private static RSAKey generateKey(String keyId) {
    try {
      return new RSAKeyGenerator(2048).keyID(keyId).generate();
    } catch (JOSEException e) {
      throw new IllegalStateException(e);
    }
  }
}
