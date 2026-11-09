package com.mairor.backend.products.imports;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.products.entity.ImportRunStatus;
import org.springframework.http.HttpStatus;

/**
 * 이미 끝난 적재 실행에는 건을 더하거나 다른 상태로 끝낼 수 없다(409). 끝난 실행에 건을 이어 붙이면 통계와 완료 시각이 맞지 않게 된다. 하트비트가 끊겨 서버가 끝낸
 * 실행({@code ABANDONED})도 같다. 수집기는 같은 {@code runId}로 새 실행을 열 수 없으므로 새 {@code runId}로 다시 시작한다.
 */
public class CatalogImportRunClosedException extends BusinessException {

  public static final String CODE = "IMPORT_RUN_CLOSED";

  public CatalogImportRunClosedException(String runId, ImportRunStatus status) {
    super(HttpStatus.CONFLICT, CODE, "이미 끝난 적재 실행입니다: " + runId + " (" + status + ")");
  }
}
