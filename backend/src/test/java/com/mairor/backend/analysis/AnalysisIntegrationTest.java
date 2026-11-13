package com.mairor.backend.analysis;

import com.mairor.backend.TestcontainersConfiguration;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 분석 작업 통합 테스트의 공통 설정. 운영처럼 스키마 SQL 을 적용해 부분 유일 인덱스(같은 영상 진행 작업 하나)까지 있는 DB 를 쓴다. 트랜잭션 롤백에 기대지 않고
 * (worker·동시 요청은 커밋이 필요하다) 테스트마다 분석 테이블을 비운다. 저장소는 이 클래스가 만든 임시 폴더다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.internal.token=" + AnalysisIntegrationTest.TOKEN,
      "app.storage.type=local",
      // 테스트 저장소는 로컬(file: 주소)이지만 프레임을 싣는 흐름을 검사하려고 켠다. 가짜 AI 는 주소를 내려받지 않는다
      "app.ai.send-frames=true"
    })
abstract class AnalysisIntegrationTest {

  static final String TOKEN = "test-internal-token";

  static final Path STORAGE_ROOT = tempDir("mairor-test-storage");
  static final Path WORK_ROOT = tempDir("mairor-test-analysis");

  @DynamicPropertySource
  static void storage(DynamicPropertyRegistry registry) {
    registry.add("app.storage.local.root", STORAGE_ROOT::toString);
    registry.add("app.analysis.worker.work-dir", WORK_ROOT::toString);
  }

  @Autowired protected JdbcTemplate jdbc;

  @Autowired
  @Qualifier("guideReferenceTaskExecutor")
  private ThreadPoolTaskExecutor guideReferenceTasks;

  @BeforeEach
  void clearAnalysisTables() {
    waitForGuideReferenceTasks();
    jdbc.update("delete from llm_calls");
    jdbc.update("delete from guide_step_product_links");
    jdbc.update("delete from guides");
    jdbc.update("delete from analysis_jobs");
    jdbc.update("delete from videos");
  }

  /**
   * 앞 테스트가 맡긴 가이드 제품 대조(AI 콜백 · 수집 결과 뒤 비동기)가 끝나기를 기다린다. 링크를 지운 뒤 대조가 링크를 새로 넣으면 가이드를 지울 때 FK 에
   * 걸린다. 큐에서 꺼낸 직후처럼 잠깐 비어 보이는 틈이 있어 연달아 세 번 비어 있어야 끝난 것으로 본다.
   */
  private void waitForGuideReferenceTasks() {
    long deadline = System.nanoTime() + Duration.ofSeconds(10).toNanos();
    int idle = 0;
    while (idle < 3) {
      boolean busy =
          guideReferenceTasks.getActiveCount() > 0
              || !guideReferenceTasks.getThreadPoolExecutor().getQueue().isEmpty();
      idle = busy ? 0 : idle + 1;
      if (System.nanoTime() > deadline) {
        throw new IllegalStateException("가이드 제품 대조 작업이 10초 안에 끝나지 않았습니다.");
      }
      try {
        Thread.sleep(20);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(e);
      }
    }
  }

  /** 저장소에 영상 파일(내용은 아무것이나)을 둔다. ffprobe 는 테스트에서 가짜로 바꾼다. */
  protected static void putObject(String key) {
    try {
      Path file = STORAGE_ROOT.resolve(key);
      Files.createDirectories(file.getParent());
      Files.writeString(file, "fake video");
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  private static Path tempDir(String prefix) {
    try {
      return Files.createTempDirectory(prefix);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }
}
