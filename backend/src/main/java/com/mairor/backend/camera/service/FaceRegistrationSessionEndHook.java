package com.mairor.backend.camera.service;

import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndHook;
import java.util.UUID;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/** 연결된 실행 사진은 395가 처리한다. 이 훅은 REGISTERED만 정리한다. */
@Component
@Order(100)
public class FaceRegistrationSessionEndHook implements SessionEndHook {
  private final FaceRegistrationLifecycleService lifecycle;

  public FaceRegistrationSessionEndHook(FaceRegistrationLifecycleService lifecycle) {
    this.lifecycle = lifecycle;
  }

  @Override
  public void beforeSessionEnds(SessionEnd end) {
    UUID userId;
    try {
      userId = UUID.fromString(end.userId());
    } catch (IllegalArgumentException e) {
      // UUID 회원이 아니면 얼굴 등록의 소유자일 수 없다. 원문/세션 ID를 로그에 남기지 않는다.
      return;
    }
    lifecycle.discardUnlinkedForSession(userId, end.sessionId());
  }
}
