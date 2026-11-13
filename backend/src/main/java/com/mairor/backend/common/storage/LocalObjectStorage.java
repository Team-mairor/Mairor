package com.mairor.backend.common.storage;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

/** 로컬 폴더를 저장소로 쓴다(개발·테스트). 키는 뿌리 폴더 아래 상대 경로이며, 뿌리 밖을 가리키는 키({@code ../})는 거절한다. */
public class LocalObjectStorage implements ObjectStorage {

  private final Path root;

  public LocalObjectStorage(Path root) {
    this.root = root.toAbsolutePath().normalize();
  }

  @Override
  public void download(String key, Path target) {
    Path source = resolve(key);
    if (!Files.isRegularFile(source)) {
      throw new ObjectNotFoundException(key);
    }
    try {
      if (target.getParent() != null) {
        Files.createDirectories(target.getParent());
      }
      Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
    } catch (IOException e) {
      throw new StorageException("로컬 저장소에서 복사하지 못했습니다: " + key, e);
    }
  }

  @Override
  public boolean exists(String key) {
    return Files.isRegularFile(resolve(key));
  }

  @Override
  public void upload(Path source, String key, String contentType) {
    Path target = resolve(key);
    try {
      Files.createDirectories(target.getParent());
      Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
    } catch (IOException e) {
      throw new StorageException("로컬 저장소에 복사하지 못했습니다: " + key, e);
    }
  }

  /** 이미 없는 파일의 삭제도 성공이다. */
  @Override
  public void delete(String key) {
    Path target = resolve(key);
    try {
      Files.deleteIfExists(target);
    } catch (IOException e) {
      throw new StorageException("로컬 객체를 삭제하지 못했습니다", e);
    }
  }

  /** 키가 폴더 경로이므로 그 폴더를 통째로 지운다. 지운 파일 수를 돌려준다. */
  @Override
  public int deletePrefix(String prefix) {
    ObjectStorage.requireFolderPrefix(prefix);
    Path dir = resolve(prefix);
    if (!Files.isDirectory(dir)) {
      return 0;
    }
    try (Stream<Path> walk = Files.walk(dir)) {
      List<Path> paths = walk.sorted(Comparator.reverseOrder()).toList();
      int files = 0;
      for (Path path : paths) {
        if (Files.isRegularFile(path)) {
          files++;
        }
        Files.deleteIfExists(path);
      }
      return files;
    } catch (IOException e) {
      throw new StorageException("로컬 폴더를 지우지 못했습니다: " + prefix, e);
    }
  }

  /** 로컬은 만료가 없다. */
  @Override
  public URI presignGet(String key, Duration ttl) {
    return resolve(key).toUri();
  }

  /** {@code file:} 주소라 다른 서버는 받지 못한다. */
  @Override
  public boolean servesHttpUrls() {
    return false;
  }

  private Path resolve(String key) {
    Path path = root.resolve(key).normalize();
    if (!path.startsWith(root)) {
      throw new IllegalArgumentException("저장소 밖을 가리키는 키입니다: " + key);
    }
    return path;
  }
}
