package com.mairor.backend.products.dto.request;

import com.mairor.backend.products.entity.ImportRunStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;

/** 적재 실행 끝내기. */
public record CatalogImportFinishRequest(
    @Schema(
            description = "COMPLETED: 수집기가 끝까지 보냈다. FAILED: 수집기가 실행을 실패로 끝냈다. 그 밖의 상태는 서버가 정한다",
            example = "COMPLETED")
        @NotNull
        Status status) {

  /** 수집기가 정할 수 있는 끝 상태. */
  public enum Status {
    COMPLETED,
    FAILED;

    public ImportRunStatus toRunStatus() {
      return ImportRunStatus.valueOf(name());
    }
  }
}
