package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.repository.UserAgreementRepository;
import com.mairor.backend.users.repository.UserRepository;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

/**
 * 실제 서버를 띄워 컨텍스트 경로({@code /api})를 거친 호출을 확인한다. {@code MockMvc}는 {@code /api}를 거치지 않으므로, 공개·CSRF
 * 제외·Origin 필터가 실제 경로에 적용되는지는 여기서만 확인된다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "app.security.allowed-origins=http://localhost:3000")
class UserSignUpContextPathTest {

  private static final String ORIGIN = "http://localhost:3000";

  @Value("${local.server.port}")
  private int port;

  @Autowired private UserRepository userRepository;
  @Autowired private UserAgreementRepository userAgreementRepository;

  private final String email = "ctx-" + UUID.randomUUID() + "@example.com";

  private record Reply(int status, String body) {}

  private RestClient client() {
    return RestClient.builder().baseUrl("http://localhost:" + port + "/api").build();
  }

  private Reply post(String origin) {
    var request = client().post().uri("/v1/users/signup").contentType(MediaType.APPLICATION_JSON);
    if (origin != null) {
      request = request.header("Origin", origin);
    }
    return request
        .body(
            """
            {"email": "%s", "password": "ExampleOnly!2026", "passwordConfirm": "ExampleOnly!2026",
             "agreements": %s}"""
                .formatted(email, SignUpRequests.AGREEMENTS_JSON))
        .exchange(
            (req, res) ->
                new Reply(
                    res.getStatusCode().value(),
                    new String(res.getBody().readAllBytes(), StandardCharsets.UTF_8)));
  }

  @AfterEach
  void cleanUp() {
    userRepository
        .findByEmail(email)
        .ifPresent(
            user -> {
              // 약관 동의 기록이 회원을 참조하므로 먼저 지운다
              userAgreementRepository.deleteAll(userAgreementRepository.findByUserId(user.getId()));
              userRepository.delete(user);
            });
  }

  @Test
  void signUp_throughTheContextPath_returns201WithoutLoginOrCsrfToken() {
    Reply reply = post(ORIGIN);

    assertThat(reply.status()).isEqualTo(201);
    assertThat((String) JsonPath.read(reply.body(), "$.email")).isEqualTo(email);
    assertThat(userRepository.existsByEmail(email)).isTrue();
  }

  @Test
  void signUp_throughTheContextPath_rejectsMissingAndForeignOrigin() {
    Reply missing = post(null);
    Reply foreign = post("https://evil.com");

    assertThat(missing.status()).isEqualTo(403);
    assertThat((String) JsonPath.read(missing.body(), "$.code")).isEqualTo("FORBIDDEN");
    assertThat(foreign.status()).isEqualTo(403);
    assertThat(userRepository.existsByEmail(email)).isFalse();
  }

  @Test
  void otherEndpoints_throughTheContextPath_stillRequireLogin() {
    Reply reply =
        client()
            .get()
            .uri("/v1/any")
            .exchange(
                (req, res) ->
                    new Reply(
                        res.getStatusCode().value(),
                        new String(res.getBody().readAllBytes(), StandardCharsets.UTF_8)));

    assertThat(reply.status()).isEqualTo(401);
  }
}
