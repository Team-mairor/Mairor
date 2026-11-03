package com.mairor.backend.common.storage;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

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

  private Path resolve(String key) {
    Path path = root.resolve(key).normalize();
    if (!path.startsWith(root)) {
      throw new IllegalArgumentException("저장소 밖을 가리키는 키입니다: " + key);
    }
    return path;
  }
}
