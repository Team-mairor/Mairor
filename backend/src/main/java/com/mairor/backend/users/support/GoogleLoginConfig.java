package com.mairor.backend.users.support;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.config.oauth2.client.CommonOAuth2Provider;

/**
 * Google 클라이언트 등록. 설정 세 값이 모두 있을 때만 등록하고, 일부만 있거나 prod 에서 비어 있으면 기동하지 않는다. 키 없는 로컬은 등록 없이 뜨고 Google
 * 로그인만 503 이 된다.
 */
@Configuration
public class GoogleLoginConfig {

  static final String REGISTRATION_ID = "google";

  private static final Logger log = LoggerFactory.getLogger(GoogleLoginConfig.class);

  /** Google 토큰·공개키 호출 한 번에 기다리는 최대 시간. 넘으면 로그인 화면에 일시 장애로 안내한다. */
  static final Duration GOOGLE_CALL_TIMEOUT = Duration.ofSeconds(5);

  @Bean
  GoogleOidcAuthenticator googleOidcAuthenticator() {
    return new GoogleOidcAuthenticator(GOOGLE_CALL_TIMEOUT);
  }

  @Bean
  @ConditionalOnProperty(
      prefix = "app.oauth.google",
      name = "state-store",
      havingValue = "memory",
      matchIfMissing = true)
  GoogleAuthorizationStore googleAuthorizationStore(GoogleLoginProperties properties) {
    return new GoogleAuthorizationStore(properties.authorizationTtl());
  }

  @Bean
  @ConditionalOnProperty(prefix = "app.oauth.google", name = "state-store", havingValue = "redis")
  GoogleAuthorizationStore redisGoogleAuthorizationStore(
      GoogleLoginProperties properties, StringRedisTemplate redis) {
    return new GoogleAuthorizationStore(properties.authorizationTtl(), redis);
  }

  @Bean
  @ConditionalOnProperty(
      prefix = "app.oauth.google",
      name = "state-store",
      havingValue = "memory",
      matchIfMissing = true)
  GoogleSignupStore googleSignupStore(GoogleLoginProperties properties) {
    return new GoogleSignupStore(properties.signupTtl());
  }

  @Bean
  @ConditionalOnProperty(prefix = "app.oauth.google", name = "state-store", havingValue = "redis")
  GoogleSignupStore redisGoogleSignupStore(
      GoogleLoginProperties properties, StringRedisTemplate redis) {
    return new GoogleSignupStore(properties.signupTtl(), redis);
  }

  @Bean
  GoogleClientRegistrations googleClientRegistrations(
      GoogleLoginProperties properties, Environment environment) {
    if (properties.partiallyConfigured()) {
      throw new IllegalStateException(
          "Google 로그인 설정이 일부만 있습니다. GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI 를 모두 설정하거나 모두 비우세요.");
    }
    if (!properties.configured()) {
      if (environment.acceptsProfiles(Profiles.of("prod"))) {
        throw new IllegalStateException(
            "운영에서 Google 로그인 설정이 비어 있습니다. GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI 를 설정하세요.");
      }
      log.warn("Google 로그인 설정이 없어 Google 로그인을 끕니다. 시작 요청은 503 입니다.");
      return new GoogleClientRegistrations(null);
    }
    // scope 기본값(openid profile email)의 openid 로 nonce·ID 토큰 검증을 타고, PKCE 는 기본값으로 켜진다
    return new GoogleClientRegistrations(
        CommonOAuth2Provider.GOOGLE
            .getBuilder(REGISTRATION_ID)
            .clientId(properties.clientId())
            .clientSecret(properties.clientSecret())
            .redirectUri(properties.redirectUri())
            .build());
  }
}
