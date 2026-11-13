package com.mairor.backend.analysis.worker;

import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/**
 * worker 작업 폴더 정리(S15P31A306-407). 작업마다 하위 폴더를 만들고 끝나면 지우지만, 컨테이너가 같은 채로 다시 떴을 때(OOM 등)는 남는다.
 * worker 가 뜰 때 아직 아무 작업도 돌지 않는 시점(빈 초기화, 스케줄 시작 전)에 작업 폴더 안을 비운다.
 */
@Component
@Profile("worker")
class WorkDirCleaner {

  private static final Logger log = LoggerFactory.getLogger(WorkDirCleaner.class);

  private final WorkerProperties properties;

  WorkDirCleaner(WorkerProperties properties) {
    this.properties = properties;
  }

  @PostConstruct
  void cleanOnStart() {
    int removed = clear(properties.workDir());
    if (removed > 0) {
      log.warn("지난 실행이 남긴 작업 폴더 {}개를 지웠습니다: {}", removed, properties.workDir());
    }
  }

  /**
   * 폴더 안의 것을 모두 지운다(폴더 자체는 남긴다). 지우지 못한 것은 로그만 남기고 넘어간다.
   *
   * @return 지운 맨 위 항목 수
   */
  static int clear(Path dir) {
    if (!Files.isDirectory(dir)) {
      return 0;
    }
    List<Path> entries;
    try (Stream<Path> list = Files.list(dir)) {
      entries = list.toList();
    } catch (IOException e) {
      log.warn("작업 폴더를 읽지 못했습니다: {}", dir, e);
      return 0;
    }
    int removed = 0;
    for (Path entry : entries) {
      try (Stream<Path> walk = Files.walk(entry)) {
        for (Path path : walk.sorted(Comparator.reverseOrder()).toList()) {
          Files.deleteIfExists(path);
        }
        removed++;
      } catch (IOException e) {
        log.warn("작업 폴더를 지우지 못했습니다: {}", entry, e);
      }
    }
    return removed;
  }
}
