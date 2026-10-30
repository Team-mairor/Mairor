package com.mairor.backend.testsupport;

import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndHook;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Supplier;
import org.springframework.session.FindByIndexNameSessionRepository;

/**
 * 테스트용 세션 종료 훅. 호출을 기록하고(호출 시점에 세션이 저장소에 있었는지 포함), {@link #failingSessionIds} 에 든 세션에서는 {@link
 * #failure} 가 만든 예외로 실패한다. {@link RecordingSessionEndHookConfig} 로 빈에 등록한다.
 */
public class RecordingSessionEndHook implements SessionEndHook {

  /** 기록된 호출 하나. */
  public record Call(SessionEnd end, boolean sessionExistedWhenCalled) {}

  public final List<Call> calls = new CopyOnWriteArrayList<>();
  public final Set<String> failingSessionIds = ConcurrentHashMap.newKeySet();

  /** 실패할 때 던질 예외. 기본은 일반 예외(500)이고, 일시적 저장소 장애(503)를 흉내 낼 때 바꾼다. */
  public volatile Supplier<RuntimeException> failure = RecordingSessionEndHook::defaultFailure;

  private final FindByIndexNameSessionRepository<?> sessions;

  public RecordingSessionEndHook(FindByIndexNameSessionRepository<?> sessions) {
    this.sessions = sessions;
  }

  @Override
  public void beforeSessionEnds(SessionEnd end) {
    calls.add(new Call(end, sessions.findById(end.sessionId()) != null));
    if (failingSessionIds.contains(end.sessionId())) {
      throw failure.get();
    }
  }

  public void reset() {
    calls.clear();
    failingSessionIds.clear();
    failure = RecordingSessionEndHook::defaultFailure;
  }

  private static RuntimeException defaultFailure() {
    return new IllegalStateException("정리 실패(테스트가 주입)");
  }
}
