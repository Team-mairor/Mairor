package com.mairor.backend.products.imports;

import com.mairor.backend.common.error.BusinessException;
import java.util.UUID;
import org.springframework.http.HttpStatus;

/** 적재 실행을 찾지 못했다(404). 건을 보내기 전에 실행을 열어야 한다. */
public class CatalogImportRunNotFoundException extends BusinessException {

  public static final String CODE = "IMPORT_RUN_NOT_FOUND";

  public CatalogImportRunNotFoundException(UUID runId) {
    super(HttpStatus.NOT_FOUND, CODE, "적재 실행을 찾을 수 없습니다: " + runId);
  }
}
