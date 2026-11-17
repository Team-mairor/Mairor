package com.mairor.backend.users.support;

import java.time.Instant;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/** JSON codec for the OAuth request fields needed to validate and redeem a callback. */
final class OAuth2AuthorizationRequestCodec {

  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final TypeReference<Stored> STORED_TYPE = new TypeReference<>() {};

  private OAuth2AuthorizationRequestCodec() {}

  static String encode(OAuth2AuthorizationRequest request, Instant expiresAt) {
    Stored stored =
        new Stored(
            request.getAuthorizationUri(),
            request.getAuthorizationRequestUri(),
            request.getClientId(),
            request.getRedirectUri(),
            request.getScopes(),
            request.getState(),
            request.getAdditionalParameters(),
            request.getAttributes(),
            expiresAt.toEpochMilli());
    try {
      return JSON.writeValueAsString(stored);
    } catch (RuntimeException e) {
      throw new IllegalStateException("Could not serialize the Google authorization request", e);
    }
  }

  static Decoded decode(String json) {
    try {
      Stored stored = JSON.readValue(json, STORED_TYPE);
      OAuth2AuthorizationRequest request =
          OAuth2AuthorizationRequest.authorizationCode()
              .authorizationUri(stored.authorizationUri())
              .clientId(stored.clientId())
              .redirectUri(stored.redirectUri())
              .scopes(stored.scopes() == null ? Set.of() : new HashSet<>(stored.scopes()))
              .state(stored.state())
              .additionalParameters(values -> putAll(values, stored.additionalParameters()))
              .attributes(values -> putAll(values, stored.attributes()))
              .authorizationRequestUri(stored.authorizationRequestUri())
              .build();
      return new Decoded(request, Instant.ofEpochMilli(stored.expiresAtMillis()));
    } catch (RuntimeException e) {
      throw new IllegalStateException("Could not deserialize the Google authorization request", e);
    }
  }

  private static void putAll(Map<String, Object> target, Map<String, Object> source) {
    if (source != null) {
      target.putAll(source);
    }
  }

  record Decoded(OAuth2AuthorizationRequest request, Instant expiresAt) {}

  private record Stored(
      String authorizationUri,
      String authorizationRequestUri,
      String clientId,
      String redirectUri,
      Set<String> scopes,
      String state,
      Map<String, Object> additionalParameters,
      Map<String, Object> attributes,
      long expiresAtMillis) {}
}
