package com.mairor.backend.common.storage;

/** 저장소에 닿지 못했거나 읽고 쓰지 못했다. 네트워크·권한·디스크 문제이며 다시 시도하면 될 수 있다. */
public class StorageException extends RuntimeException {

  public StorageException(String message, Throwable cause) {
    super(message, cause);
  }
}
