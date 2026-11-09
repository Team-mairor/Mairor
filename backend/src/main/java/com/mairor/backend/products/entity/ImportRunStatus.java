package com.mairor.backend.products.entity;

/** 카탈로그 적재 실행의 상태. {@link #RUNNING}이 아니면 끝난 실행이고 {@code finished_at}이 있다. */
public enum ImportRunStatus {
  /** 진행 중이다. 하트비트가 끊기면 {@link #ABANDONED}로 끝낸다. */
  RUNNING,
  /** 수집기가 끝났다고 알렸다. 건별 실패가 있어도 실행은 끝난 것이다(실패는 건에 남는다). */
  COMPLETED,
  /** 수집기가 실행을 실패로 끝냈다. */
  FAILED,
  /** 하트비트가 제한 시간 안에 오지 않아 서버가 끝냈다. */
  ABANDONED;

  public boolean isFinished() {
    return this != RUNNING;
  }
}
