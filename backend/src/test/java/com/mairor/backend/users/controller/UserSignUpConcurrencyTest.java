package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.mairor.backend.TestcontainersConfiguration;
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
 * 같은 이메일로 동시에 가입해도 정확히 한 건만 만들어지고 나머지는 409인지 확인한다. 스레드마다 별도 트랜잭션이어야 하므로 {@code @Transactional}을 붙이지
 * 않고, 커밋된 데이터는 끝나고 직접 지운다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = "app.security.allowed-origins=http://localhost:3000")
@AutoConfigureMockMvc
class UserSignUpConcurrencyTest {

  private static final int ATTEMPTS = 8;

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;

  private final String email = "race-" + UUID.randomUUID() + "@example.com";

  @AfterEach
  void cleanUp() {
    userRepository.findByEmail(email).ifPresent(userRepository::delete);
  }

  @Test
  void sameEmailAtTheSameTime_createsExactlyOneUser() throws Exception {
    String json =
        """
        {"email": "%s", "password": "ExampleOnly!2026", "passwordConfirm": "ExampleOnly!2026"}"""
            .formatted(email);
    ExecutorService pool = Executors.newFixedThreadPool(ATTEMPTS);
    CountDownLatch ready = new CountDownLatch(ATTEMPTS);
    CountDownLatch go = new CountDownLatch(1);
    List<Future<Integer>> results = new ArrayList<>();
    try {
      for (int i = 0; i < ATTEMPTS; i++) {
        results.add(
            pool.submit(
                () -> {
                  ready.countDown();
                  go.await();
                  return mockMvc
                      .perform(
                          post("/v1/users")
                              .header("Origin", "http://localhost:3000")
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

      assertThat(statuses).filteredOn(s -> s == 201).hasSize(1);
      assertThat(statuses).filteredOn(s -> s == 409).hasSize(ATTEMPTS - 1);
      assertThat(statuses).doesNotContain(500);
      assertThat(userRepository.findByEmail(email)).isPresent();
    } finally {
      pool.shutdownNow();
    }
  }
}
