package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.AnnotationAwareOrderComparator;

class SessionEndNotifierTest {

  private static final SessionEnd END =
      new SessionEnd("user-1", "secret-session-id", SessionEndReason.LOGOUT);

  private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
  private final List<String> calls = new ArrayList<>();

  /** 호출 기록을 남기고, 필요하면 실패하는 훅. 순서는 {@link Ordered} 로 정한다. */
  private final class RecordingHook implements SessionEndHook, Ordered {
    private final String name;
    private final int order;
    private final RuntimeException failure;

    RecordingHook(String name, int order, RuntimeException failure) {
      this.name = name;
      this.order = order;
      this.failure = failure;
    }

    @Override
    public void beforeSessionEnds(SessionEnd end) {
      calls.add(name);
      if (failure != null) {
        throw failure;
      }
    }

    @Override
    public int getOrder() {
      return order;
    }
  }

  private SessionEndNotifier notifierWith(SessionEndHook... hooks) {
    DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
    factory.setDependencyComparator(AnnotationAwareOrderComparator.INSTANCE);
    for (int i = 0; i < hooks.length; i++) {
      factory.registerSingleton("hook" + i, hooks[i]);
    }
    return new SessionEndNotifier(
        factory.getBeanProvider(SessionEndHook.class), new SessionMetrics(registry));
  }

  private double failures(String reason) {
    var counter = registry.find("mairor.session.end_hook.failures").tag("reason", reason).counter();
    return counter == null ? 0 : counter.count();
  }

  // ---- 호출 순서 ----

  @Test
  void hooksAreCalledInTheirOrder() {
    SessionEndNotifier notifier =
        notifierWith(
            new RecordingHook("third", 30, null),
            new RecordingHook("first", 10, null),
            new RecordingHook("second", 20, null));

    notifier.strict(END);

    assertThat(calls).containsExactly("first", "second", "third");
  }

  @Test
  void theHookReceivesTheSessionThatIsEnding() {
    List<SessionEnd> received = new ArrayList<>();
    SessionEndNotifier notifier = notifierWith((SessionEndHook) received::add);

    notifier.strict(END);
    notifier.bestEffort(new SessionEnd("user-2", "other", SessionEndReason.ABSOLUTE_EXPIRED));

    assertThat(received)
        .extracting(SessionEnd::userId, SessionEnd::reason)
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple("user-1", SessionEndReason.LOGOUT),
            org.assertj.core.groups.Tuple.tuple("user-2", SessionEndReason.ABSOLUTE_EXPIRED));
  }

  @Test
  void withoutAnyHookNothingHappens() {
    SessionEndNotifier notifier = notifierWith();

    notifier.strict(END);
    notifier.bestEffort(END);

    assertThat(registry.getMeters()).isEmpty();
  }

  // ---- 엄격 ----

  @Test
  void strictRethrowsTheFailureAndDoesNotCallTheLaterHooks() {
    IllegalStateException failure = new IllegalStateException("cannot clean up");
    SessionEndNotifier notifier =
        notifierWith(
            new RecordingHook("ok", 10, null),
            new RecordingHook("broken", 20, failure),
            new RecordingHook("later", 30, null));

    assertThatThrownBy(() -> notifier.strict(END)).isSameAs(failure);

    assertThat(calls).containsExactly("ok", "broken");
    assertThat(failures("logout")).isEqualTo(1);
  }

  // ---- 최선 ----

  @Test
  void bestEffortSwallowsTheFailureAndStillCallsTheLaterHooks() {
    SessionEndNotifier notifier =
        notifierWith(
            new RecordingHook("broken", 10, new IllegalStateException("boom")),
            new RecordingHook("later", 20, null));

    notifier.bestEffort(END);

    assertThat(calls).containsExactly("broken", "later");
    assertThat(failures("logout")).isEqualTo(1);
  }

  @Test
  void everyFailingHookIsCounted() {
    SessionEndNotifier notifier =
        notifierWith(
            new RecordingHook("a", 10, new IllegalStateException("1")),
            new RecordingHook("b", 20, new IllegalStateException("2")));

    notifier.bestEffort(new SessionEnd("u", "s", SessionEndReason.IDLE_EXPIRED));

    assertThat(failures("idle_expired")).isEqualTo(2);
  }

  // ---- 지표 ----

  @Test
  void failuresAreLabelledByReasonOnly() {
    SessionEndNotifier notifier =
        notifierWith(new RecordingHook("broken", 10, new IllegalStateException("boom")));

    notifier.bestEffort(new SessionEnd("user-1", "secret-session-id", SessionEndReason.LOGOUT));
    notifier.bestEffort(new SessionEnd("user-2", "other-secret", SessionEndReason.LOGOUT));

    assertThat(registry.getMeters())
        .allSatisfy(
            meter ->
                assertThat(meter.getId().getTags())
                    .allSatisfy(
                        tag -> {
                          assertThat(tag.getKey()).isEqualTo("reason");
                          assertThat(tag.getValue())
                              .doesNotContain("user")
                              .doesNotContain("secret");
                        }));
  }

  @Test
  void aSuccessfulHookIsNotCountedAsAFailure() {
    SessionEndNotifier notifier = notifierWith(new RecordingHook("ok", 10, null));

    notifier.strict(END);

    assertThat(registry.getMeters()).isEmpty();
  }

  // ---- 값 객체 ----

  @Test
  void theSessionIdIsNotPrintedByToString() {
    assertThat(END.toString()).doesNotContain("secret-session-id").contains("user-1");
  }

  @Test
  void aSessionEndNeedsAUserASessionAndAReason() {
    assertThatThrownBy(() -> new SessionEnd(null, "s", SessionEndReason.LOGOUT))
        .isInstanceOf(NullPointerException.class);
    assertThatThrownBy(() -> new SessionEnd("u", null, SessionEndReason.LOGOUT))
        .isInstanceOf(NullPointerException.class);
    assertThatThrownBy(() -> new SessionEnd("u", "s", null))
        .isInstanceOf(NullPointerException.class);
    assertThatThrownBy(() -> new SessionEnd(" ", "s", SessionEndReason.LOGOUT))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new SessionEnd("u", "", SessionEndReason.LOGOUT))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void everyReasonHasALowerCaseMetricLabel() {
    for (SessionEndReason reason : SessionEndReason.values()) {
      assertThat(reason.name().toLowerCase(java.util.Locale.ROOT)).matches("[a-z_]+");
    }
    assertThat(SessionEndReason.values())
        .extracting(Enum::name)
        .containsExactly(
            "LOGOUT",
            "ALL_DEVICES_REVOKED",
            "REPLACED_BY_LOGIN",
            "ABSOLUTE_EXPIRED",
            "IDLE_EXPIRED");
  }
}
