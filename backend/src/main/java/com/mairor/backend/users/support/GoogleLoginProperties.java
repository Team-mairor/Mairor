package com.mairor.backend.users.support;

import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.hibernate.validator.constraints.time.DurationMin;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.StringUtils;
import org.springframework.validation.annotation.Validated;

/**
 * Google 로그인 설정 ({@code app.oauth.google.*}). Boot 의 자동 등록({@code
 * spring.security.oauth2.client.*})은 빈 client-id 로 기동이 실패해서 쓰지 않고, 세 값이 모두 있을 때만 {@link
 * GoogleLoginConfig} 가 클라이언트를 직접 등록한다.
 *
 * @param clientId GCP OAuth 클라이언트 ID
 * @param clientSecret GCP OAuth 클라이언트 보안 비밀
 * @param redirectUri Google 에 등록한 callback 주소. 브라우저가 FE 와 같은 호스트로 돌아오도록 FE 주소의 {@code /api/...} 를
 *     쓴다
 * @param authorizationTtl 로그인 시작부터 callback 까지 허용하는 시간 (0보다 길어야 한다)
 * @param signupTtl 처음 온 사용자가 callback 뒤 가입을 마치기까지 허용하는 시간 (0보다 길어야 한다)
 */
@Validated
@ConfigurationProperties(prefix = "app.oauth.google")
public record GoogleLoginProperties(
    String clientId,
    String clientSecret,
    String redirectUri,
    @NotNull @DurationMin(nanos = 0, inclusive = false) Duration authorizationTtl,
    @NotNull @DurationMin(nanos = 0, inclusive = false) Duration signupTtl) {

  /** 클라이언트 등록에 필요한 세 값이 모두 있다. */
  public boolean configured() {
    return StringUtils.hasText(clientId)
        && StringUtils.hasText(clientSecret)
        && StringUtils.hasText(redirectUri);
  }

  /** 세 값 중 일부만 있다. 설정 실수로 보고 기동하지 않는다. */
  boolean partiallyConfigured() {
    return !configured()
        && (StringUtils.hasText(clientId)
            || StringUtils.hasText(clientSecret)
            || StringUtils.hasText(redirectUri));
  }

  /** 보안 비밀이 로그에 남지 않도록 마스킹한다 (record 기본 toString은 값을 그대로 찍는다). */
  @Override
  public String toString() {
    return "GoogleLoginProperties[clientId="
        + clientId
        + ", clientSecret="
        + (StringUtils.hasText(clientSecret) ? "****" : "")
        + ", redirectUri="
        + redirectUri
        + ", authorizationTtl="
        + authorizationTtl
        + ", signupTtl="
        + signupTtl
        + "]";
  }
}
