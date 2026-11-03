package com.mairor.backend.common.storage;

/** 저장소에 그 키의 객체가 없다. */
public class ObjectNotFoundException extends RuntimeException {

  public ObjectNotFoundException(String key) {
    super("저장소에 객체가 없습니다: " + key);
  }
}
