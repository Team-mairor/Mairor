package com.mairor.backend.testsupport;

import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndHook;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.session.FindByIndexNameSessionRepository;

/**
 * 테스트용 세션 종료 훅. 호출을 기록하고(호출 시점에 세션이 저장소에 있었는지 포함), {@link #failingSessionIds} 에 든 세션에서는 실패한다.
 * {@link RecordingSessionEndHookConfig} 로 빈에 등록한다.
 */
public class RecordingSessionEndHook implements SessionEndHook {

  /** 기록된 호출 하나. */
  public record Call(SessionEnd end, boolean sessionExistedWhenCalled) {}

  public final List<Call> calls = new CopyOnWriteArrayList<>();
  public final Set<String> failingSessionIds = ConcurrentHashMap.newKeySet();
  private final FindByIndexNameSessionRepository<?> sessions;

  public RecordingSessionEndHook(FindByIndexNameSessionRepository<?> sessions) {
    this.sessions = sessions;
  }

  @Override
  public void beforeSessionEnds(SessionEnd end) {
    calls.add(new Call(end, sessions.findById(end.sessionId()) != null));
    if (failingSessionIds.contains(end.sessionId())) {
      throw new IllegalStateException("정리 실패(테스트가 주입)");
    }
  }

  public void reset() {
    calls.clear();
    failingSessionIds.clear();
  }
}
