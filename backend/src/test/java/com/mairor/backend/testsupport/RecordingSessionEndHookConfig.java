package com.mairor.backend.testsupport;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.session.FindByIndexNameSessionRepository;

/** {@link RecordingSessionEndHook} 을 훅 빈으로 등록한다. 테스트에 {@code @Import} 해서 쓴다. */
@TestConfiguration(proxyBeanMethods = false)
public class RecordingSessionEndHookConfig {

  @Bean
  RecordingSessionEndHook recordingSessionEndHook(FindByIndexNameSessionRepository<?> sessions) {
    return new RecordingSessionEndHook(sessions);
  }
}
