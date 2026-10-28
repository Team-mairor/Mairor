package com.mairor.backend.common.web;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 시간에 의존하는 로직(나이 계산, 요청 제한 등)이 {@link Clock}을 주입받게 해서 테스트에서 시각을 고정할 수 있게 한다. */
@Configuration
public class ClockConfig {

  @Bean
  Clock clock() {
    return Clock.systemUTC();
  }
}
