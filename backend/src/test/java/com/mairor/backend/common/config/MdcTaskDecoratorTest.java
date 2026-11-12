package com.mairor.backend.common.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

class MdcTaskDecoratorTest {

  private final ExecutorService pool = Executors.newSingleThreadExecutor();

  @AfterEach
  void stop() throws InterruptedException {
    MDC.clear();
    pool.shutdownNow();
    pool.awaitTermination(5, TimeUnit.SECONDS);
  }

  @Test
  void theCallersFieldsGoToTheOtherThreadAndAreClearedAfterwards() throws Exception {
    MDC.put("analysis_job_id", "job-1");
    AtomicReference<String> seen = new AtomicReference<>();
    pool.submit(new MdcTaskDecorator().decorate(() -> seen.set(MDC.get("analysis_job_id")))).get();
    assertThat(seen).hasValue("job-1");

    // 같은 스레드가 다음 일을 할 때 앞 일의 칸이 남지 않는다
    MDC.clear();
    pool.submit(() -> seen.set(MDC.get("analysis_job_id"))).get();
    assertThat(seen.get()).isNull();
  }

  @Test
  void callablesAlsoCarryTheFields() throws Exception {
    MDC.put("job_id", "ai-1");
    String value = pool.submit(MdcTaskDecorator.withCurrentContext(() -> MDC.get("job_id"))).get();
    assertThat(value).isEqualTo("ai-1");
  }
}
