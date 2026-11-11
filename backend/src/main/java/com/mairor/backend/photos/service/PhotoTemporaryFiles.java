package com.mairor.backend.photos.service;

import com.mairor.backend.common.storage.StorageException;
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 요청 파일 잠금은 업로드 종료까지 유지한다. 프로세스 종료 시 OS가 해제하므로 잔존 파일을 복구할 수 있다. */
@Component
@EnableScheduling
public class PhotoTemporaryFiles {
  private static final Logger log = LoggerFactory.getLogger(PhotoTemporaryFiles.class);
  private final Path directory;
  private final Clock clock;

  public PhotoTemporaryFiles(
      @Value("${app.photos.temp-directory:${java.io.tmpdir}/mairor-photo-uploads}") Path directory,
      Clock clock) {
    this.directory = directory.toAbsolutePath().normalize();
    this.clock = clock;
  }

  public Lease create() {
    Path path = null;
    FileChannel channel = null;
    try {
      Files.createDirectories(directory);
      path = Files.createTempFile(directory, "photo-", ".upload");
      // Windows에서는 사진 자체에 잠그면 디코더의 읽기/쓰기도 차단된다.
      channel =
          FileChannel.open(lockPath(path), StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
      return new Lease(path, channel, channel.lock());
    } catch (IOException | RuntimeException e) {
      try {
        if (channel != null) channel.close();
        if (path != null) {
          Files.deleteIfExists(path);
          Files.deleteIfExists(lockPath(path));
        }
      } catch (IOException cleanup) {
        e.addSuppressed(cleanup);
      }
      throw new StorageException("사진 임시 파일을 만들지 못했습니다", e);
    }
  }

  @EventListener(ApplicationReadyEvent.class)
  @Scheduled(
      fixedDelayString = "${app.photos.temp-cleanup-interval:10m}",
      initialDelayString = "${app.photos.temp-cleanup-interval:10m}")
  public void sweep() {
    if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)) return;
    try (var paths = Files.newDirectoryStream(directory, "photo-*.upload")) {
      for (Path path : paths) {
        try {
          if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
              || Files.getLastModifiedTime(path, LinkOption.NOFOLLOW_LINKS)
                  .toInstant()
                  .isAfter(clock.instant().minus(Duration.ofHours(1)))) continue;
          // 다른 JVM/요청이 업로드 중이면 건드리지 않는다.
          boolean unlocked;
          try (var channel =
              FileChannel.open(
                  lockPath(path),
                  StandardOpenOption.CREATE,
                  StandardOpenOption.WRITE,
                  LinkOption.NOFOLLOW_LINKS)) {
            try (var lock = channel.tryLock()) {
              unlocked = lock != null;
            }
          }
          if (unlocked) {
            Files.deleteIfExists(path);
            Files.deleteIfExists(lockPath(path));
          }
        } catch (OverlappingFileLockException e) {
          // 같은 JVM의 활성 요청.
        } catch (IOException e) {
          log.warn("사진 임시 파일 정리 실패. 다음 주기에 재시도한다");
        }
      }
    } catch (IOException e) {
      log.warn("사진 임시 디렉터리 조회 실패. 다음 주기에 재시도한다");
    }
  }

  private static Path lockPath(Path path) {
    return path.resolveSibling(path.getFileName() + ".lock");
  }

  public record Lease(Path path, FileChannel channel, FileLock lock) implements AutoCloseable {
    @Override
    public void close() {
      try {
        try {
          if (lock.isValid()) lock.release();
        } finally {
          channel.close();
        }
        Files.deleteIfExists(path);
        Files.deleteIfExists(lockPath(path));
      } catch (IOException e) {
        throw new StorageException("사진 임시 파일을 정리하지 못했습니다", e);
      }
    }
  }
}
