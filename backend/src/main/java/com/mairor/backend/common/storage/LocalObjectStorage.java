package com.mairor.backend.common.storage;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;

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

  /** 로컬은 만료가 없다. */
  @Override
  public URI presignGet(String key, Duration ttl) {
    return resolve(key).toUri();
  }

  private Path resolve(String key) {
    Path path = root.resolve(key).normalize();
    if (!path.startsWith(root)) {
      throw new IllegalArgumentException("저장소 밖을 가리키는 키입니다: " + key);
    }
    return path;
  }
}
