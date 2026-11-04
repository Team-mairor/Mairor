package com.mairor.backend.analysis.sse;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.analysis.controller.AnalysisJobEventsController;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

/**
 * worker 프로세스(운영 {@code prod,worker})는 SSE 를 띄우지 않는다. worker 의 상태 변경은 DB 변경 알림으로 api 에 가고, SSE
 * 연결·LISTEN·주기 작업은 api 에만 있다. worker 가 SSE 빈 없이도 뜨는지 본다.
 */
@Import(TestcontainersConfiguration.class)
@ActiveProfiles("worker")
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
class SseWorkerProfileTest {

  @Autowired private ApplicationContext context;

  @Test
  void workerStartsWithoutTheSseBeans() {
    assertThat(context.getBeanNamesForType(SseHub.class)).isEmpty();
    assertThat(context.getBeanNamesForType(PgNotificationListener.class)).isEmpty();
    assertThat(context.getBeanNamesForType(SseMaintenance.class)).isEmpty();
    assertThat(context.getBeanNamesForType(AnalysisJobEventsController.class)).isEmpty();
  }
}
