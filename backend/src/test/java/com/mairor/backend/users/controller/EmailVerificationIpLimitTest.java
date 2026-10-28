package com.mairor.backend.users.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.transaction.annotation.Transactional;

/**
 * 인증번호 발송은 이메일마다 쿨다운·시간당 횟수를 제한하지만, 한 곳에서 여러 이메일로 보내 메일을 쏟아내는 것은 클라이언트(IP) 기준 제한이 막는다. 한도를 3회로 낮춰
 * 확인한다. 이 테스트는 개발용 로깅 발송기(메일 미발송)를 쓴다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.mail.enabled=false",
      "app.rate-limit.email-verification.limit=3",
      "app.rate-limit.email-verification.window=10m"
    })
@AutoConfigureMockMvc
@Transactional
class EmailVerificationIpLimitTest {

  @Autowired private MockMvc mockMvc;

  private final String ip =
      "172.16." + (int) (Math.random() * 250) + "." + (int) (Math.random() * 250);

  private ResultActions send(String remoteAddr) throws Exception {
    return mockMvc.perform(
        post("/v1/users/email-verification")
            .header("Origin", "http://localhost:3000")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"email\": \"ip-" + UUID.randomUUID() + "@example.com\"}")
            .with(
                r -> {
                  r.setRemoteAddr(remoteAddr);
                  return r;
                }));
  }

  @Test
  void manyDifferentEmailsFromOneClient_areLimited() throws Exception {
    for (int i = 0; i < 3; i++) {
      send(ip).andExpect(status().isAccepted());
    }

    send(ip)
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_SEND_RATE_LIMITED"))
        .andExpect(header().exists("Retry-After"));
  }

  @Test
  void anotherClientIsNotAffected() throws Exception {
    for (int i = 0; i < 4; i++) {
      send(ip);
    }

    send("192.0.2." + (int) (Math.random() * 250)).andExpect(status().isAccepted());
  }

  @Test
  void spoofedForwardedForDoesNotEscapeTheLimit() throws Exception {
    for (int i = 0; i < 3; i++) {
      send(ip).andExpect(status().isAccepted());
    }

    mockMvc
        .perform(
            post("/v1/users/email-verification")
                .header("Origin", "http://localhost:3000")
                .header("X-Forwarded-For", "203.0.113.77")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\": \"ip-" + UUID.randomUUID() + "@example.com\"}")
                .with(
                    r -> {
                      r.setRemoteAddr(ip);
                      return r;
                    }))
        .andExpect(status().isTooManyRequests());
  }
}
