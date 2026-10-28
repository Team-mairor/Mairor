package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.VerificationTestSupport;
import com.mairor.backend.users.VerificationTestSupport.CapturingMailSender;
import com.mairor.backend.users.repository.UserAgreementRepository;
import com.mairor.backend.users.repository.UserRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * 같은 이메일·같은 인증 토큰으로 동시에 가입해도 정확히 한 건만 만들어지고 회원·약관 기록이 일관되는지 확인한다. 스레드마다 별도 트랜잭션이어야 해서
 * {@code @Transactional}을 붙이지 않고, 커밋된 데이터는 끝나고 직접 지운다.
 */
@Import({TestcontainersConfiguration.class, VerificationTestSupport.TestBeans.class})
@SpringBootTest(
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.signup.require-email-verification=true"
    })
@AutoConfigureMockMvc
class UserSignUpEmailVerificationConcurrencyTest {

  private static final int ATTEMPTS = 8;
  private static final String ORIGIN = "http://localhost:3000";

  @Autowired private MockMvc mockMvc;
  @Autowired private CapturingMailSender mail;
  @Autowired private UserRepository userRepository;
  @Autowired private UserAgreementRepository userAgreementRepository;

  private final String email = "race-verify-" + UUID.randomUUID() + "@example.com";

  @AfterEach
  void cleanUp() {
    userRepository
        .findByEmail(email)
        .ifPresent(
            user -> {
              userAgreementRepository.deleteAll(userAgreementRepository.findByUserId(user.getId()));
              userRepository.delete(user);
            });
  }

  private String verify() throws Exception {
    mockMvc
        .perform(
            post("/v1/users/email-verification")
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\": \"" + email + "\"}"))
        .andExpect(status().isAccepted());
    String code = mail.last().code();
    String json =
        mockMvc
            .perform(
                post("/v1/users/email-verification/verification")
                    .header("Origin", ORIGIN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"email\": \"" + email + "\", \"code\": \"" + code + "\"}"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    return JsonPath.read(json, "$.verificationToken");
  }

  @Test
  void sameEmailAndTokenAtTheSameTime_createsExactlyOneUser() throws Exception {
    String token = verify();
    String json =
        """
        {"email": "%s", "password": "ExampleOnly!2026", "passwordConfirm": "ExampleOnly!2026",
         "agreements": %s, "emailVerificationToken": "%s"}"""
            .formatted(email, SignUpRequests.AGREEMENTS_JSON, token);
    ExecutorService pool = Executors.newFixedThreadPool(ATTEMPTS);
    CountDownLatch ready = new CountDownLatch(ATTEMPTS);
    CountDownLatch go = new CountDownLatch(1);
    try {
      List<Future<Integer>> results = new ArrayList<>();
      for (int i = 0; i < ATTEMPTS; i++) {
        results.add(
            pool.submit(
                () -> {
                  ready.countDown();
                  go.await();
                  return mockMvc
                      .perform(
                          post("/v1/users/signup")
                              .header("Origin", ORIGIN)
                              .contentType(MediaType.APPLICATION_JSON)
                              .content(json))
                      .andReturn()
                      .getResponse()
                      .getStatus();
                }));
      }
      assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
      go.countDown();

      List<Integer> statuses = new ArrayList<>();
      for (Future<Integer> result : results) {
        statuses.add(result.get(30, TimeUnit.SECONDS));
      }

      // 이긴 요청은 정확히 하나. 졌지만 토큰을 읽은 요청은 409, 이긴 요청이 토큰을 지운 뒤에 온 요청은 400(인증 안 됨)이다
      assertThat(statuses).filteredOn(s -> s == 201).hasSize(1);
      assertThat(statuses).doesNotContain(500);
      assertThat(statuses).allMatch(s -> s == 201 || s == 409 || s == 400);

      var user = userRepository.findByEmail(email).orElseThrow();
      assertThat(user.getEmailVerifiedAt()).isNotNull();
      assertThat(userAgreementRepository.findByUserId(user.getId())).hasSize(4);
    } finally {
      pool.shutdownNow();
    }
  }
}
