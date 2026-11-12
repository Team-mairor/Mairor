package com.mairor.backend.users.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

/** Google 설정이 없는 환경(키 없는 로컬)에서는 앱은 뜨고 Google 로그인 시작만 503 이다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "app.security.allowed-origins=http://localhost:3000",
      "app.oauth.google.client-id=",
      "app.oauth.google.client-secret=",
      "app.oauth.google.redirect-uri="
    })
@AutoConfigureMockMvc
class GoogleLoginUnavailableTest {

  @Autowired private MockMvc mockMvc;

  @Test
  void startWithoutConfiguration_redirectsToLoginWithoutCreatingCookie() throws Exception {
    mockMvc
        .perform(get("/v1/users/oauth/google"))
        .andExpect(status().isFound())
        .andExpect(
            header().string(HttpHeaders.LOCATION, "/login?error=USERS_GOOGLE_AUTH_UNAVAILABLE"))
        .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
        .andExpect(header().doesNotExist(HttpHeaders.SET_COOKIE));
  }
}
