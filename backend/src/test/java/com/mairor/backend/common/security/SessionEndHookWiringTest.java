package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.core.annotation.Order;

/**
 * 애플리케이션 컨텍스트에서 {@link SessionEndHook} 빈을 등록하면 {@link SessionEndNotifier} 가 호출해 준다. GUIDE-011 같은 다른
 * 이슈가 구현체를 빈으로 등록하는 방식 그대로를 확인한다.
 */
@Import({TestcontainersConfiguration.class, SessionEndHookWiringTest.Hooks.class})
@SpringBootTest
class SessionEndHookWiringTest {

  static final List<String> CALLS = new ArrayList<>();

  @TestConfiguration(proxyBeanMethods = false)
  static class Hooks {

    @Bean
    @Order(20)
    SessionEndHook second() {
      return end -> CALLS.add("second:" + end.reason());
    }

    @Bean
    @Order(10)
    SessionEndHook first() {
      return end -> CALLS.add("first:" + end.reason());
    }
  }

  @Autowired private SessionEndNotifier notifier;

  @BeforeEach
  void clear() {
    CALLS.clear();
  }

  @Test
  void registeredHookBeansAreCalledInOrderThroughTheNotifier() {
    notifier.strict(new SessionEnd("user-1", "session-1", SessionEndReason.DEVICE_REVOKED));

    assertThat(CALLS).containsExactly("first:DEVICE_REVOKED", "second:DEVICE_REVOKED");
  }
}
