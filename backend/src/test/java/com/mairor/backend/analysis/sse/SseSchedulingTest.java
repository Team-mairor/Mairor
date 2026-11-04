package com.mairor.backend.analysis.sse;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.scheduling.config.ScheduledTaskHolder;

/**
 * 운영 api-b 와 같은 조건(worker 아님 · 만료 세션 정리 꺼짐 {@code SESSION_SWEEP_ENABLED=false})에서도 SSE 주기 작업(ping ·
 * 상태 맞추기)이 스케줄에 올라가는지 본다. 두 기존 {@code @EnableScheduling}(worker, 세션 정리)이 모두 없는 조건이다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.session.sweep.enabled=false"
    })
class SseSchedulingTest {

  @Autowired private ApplicationContext context;
  @Autowired private List<ScheduledTaskHolder> holders;

  @Test
  void sseTasksAreScheduledEvenWhenTheSessionSweepIsOff() {
    assertThat(context.containsBean("expiredSessionSweepScheduler"))
        .as("api-b 조건: 세션 정리가 없다")
        .isFalse();

    List<String> scheduled =
        holders.stream()
            .flatMap(holder -> holder.getScheduledTasks().stream())
            .map(task -> String.valueOf(task.getTask().getRunnable()))
            .toList();

    assertThat(scheduled)
        .anyMatch(task -> task.endsWith("SseMaintenance.ping"))
        .anyMatch(task -> task.endsWith("SseMaintenance.reconcile"));
  }
}
