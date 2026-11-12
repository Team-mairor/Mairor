package com.mairor.backend.guides.config;

import com.mairor.backend.common.config.MdcTaskDecorator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

/** 분석 콜백 응답과 분리해 가이드 제품 대조를 수행한다. */
@Configuration
public class GuideReferenceExecutorConfiguration {

  @Bean(name = "guideReferenceTaskExecutor")
  ThreadPoolTaskExecutor guideReferenceTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("guide-reference-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(15);
    // 대조를 맡긴 콜백 처리의 로그 칸(분석 작업 ID 등)을 넘긴다
    executor.setTaskDecorator(new MdcTaskDecorator());
    return executor;
  }
}
