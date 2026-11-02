package com.mairor.backend.users.support;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.security.oauth2.client.authentication.OAuth2LoginAuthenticationToken;
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.http.OAuth2ErrorResponseErrorHandler;
import org.springframework.security.oauth2.client.oidc.authentication.OidcAuthorizationCodeAuthenticationProvider;
import org.springframework.security.oauth2.client.oidc.authentication.OidcIdTokenDecoderFactory;
import org.springframework.security.oauth2.client.oidc.authentication.OidcIdTokenValidator;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationExchange;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationResponse;
import org.springframework.security.oauth2.core.http.converter.OAuth2AccessTokenResponseHttpMessageConverter;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;

/**
 * Google callback 의 code 를 토큰으로 바꾸고 ID 토큰을 검증한다. 검증은 Spring 의 {@link
 * OidcAuthorizationCodeAuthenticationProvider} 가 한다: state 비교, code 교환(PKCE verifier 포함), ID 토큰
 * 서명·iss·aud·exp·nonce.
 *
 * <p>기본 구성과 다른 점은 둘이다. Google 호출(토큰·공개키)에 시간 제한을 두고(기본값은 무제한이라 Google 이 느리면 요청 스레드가 묶인다), userinfo
 * 는 부르지 않는다(필요한 sub·email·email_verified·name 이 ID 토큰에 있다). 액세스 토큰은 쓰지 않고 버린다.
 */
public class GoogleOidcAuthenticator {

  private final OidcAuthorizationCodeAuthenticationProvider provider;

  /** 공개키 주소별 디코더. 디코더가 공개키를 캐시하므로 요청마다 만들지 않는다. */
  private final Map<String, JwtDecoder> decoders = new ConcurrentHashMap<>();

  private final RestTemplate jwkClient;

  public GoogleOidcAuthenticator(Duration timeout) {
    SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
    requestFactory.setConnectTimeout(timeout);
    requestFactory.setReadTimeout(timeout);

    RestClientAuthorizationCodeTokenResponseClient tokenClient =
        new RestClientAuthorizationCodeTokenResponseClient();
    tokenClient.setRestClient(
        RestClient.builder()
            .requestFactory(requestFactory)
            // 기본 구성과 같은 변환기 두 개만 쓴다. 기본 JSON 변환기가 토큰 응답을 먼저 가져가지 않게 한다
            .configureMessageConverters(
                converters ->
                    converters
                        .disableDefaults()
                        .addCustomConverter(new FormHttpMessageConverter())
                        .addCustomConverter(new OAuth2AccessTokenResponseHttpMessageConverter()))
            .defaultStatusHandler(new OAuth2ErrorResponseErrorHandler())
            .build());
    this.jwkClient = new RestTemplate(requestFactory);

    OidcUserService userService = new OidcUserService();
    userService.setRetrieveUserInfo(request -> false);

    this.provider = new OidcAuthorizationCodeAuthenticationProvider(tokenClient, userService);
    this.provider.setJwtDecoderFactory(this::decoder);
  }

  /**
   * code 를 교환하고 검증한 Google 사용자를 돌려준다.
   *
   * @throws OAuth2AuthenticationException state 불일치, 교환 실패, ID 토큰 검증 실패, Google 호출 실패
   */
  public OidcUser authenticate(
      ClientRegistration registration,
      OAuth2AuthorizationRequest authorization,
      String state,
      String code) {
    OAuth2AuthorizationResponse response =
        OAuth2AuthorizationResponse.success(code)
            .redirectUri(authorization.getRedirectUri())
            .state(state)
            .build();
    OAuth2LoginAuthenticationToken result =
        (OAuth2LoginAuthenticationToken)
            provider.authenticate(
                new OAuth2LoginAuthenticationToken(
                    registration, new OAuth2AuthorizationExchange(authorization, response)));
    return (OidcUser) result.getPrincipal();
  }

  private JwtDecoder decoder(ClientRegistration registration) {
    String jwkSetUri = registration.getProviderDetails().getJwkSetUri();
    return decoders.computeIfAbsent(
        jwkSetUri,
        uri -> {
          NimbusJwtDecoder decoder =
              NimbusJwtDecoder.withJwkSetUri(uri)
                  .jwsAlgorithm(SignatureAlgorithm.RS256)
                  .restOperations(jwkClient)
                  .build();
          decoder.setJwtValidator(new OidcIdTokenValidator(registration));
          decoder.setClaimSetConverter(OidcIdTokenDecoderFactory.createDefaultClaimTypeConverter());
          return decoder;
        });
  }
}
