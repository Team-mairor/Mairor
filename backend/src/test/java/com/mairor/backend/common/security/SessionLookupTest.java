package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.MapSession;

class SessionLookupTest {

  @SuppressWarnings("unchecked")
  private final FindByIndexNameSessionRepository<MapSession> sessions =
      mock(FindByIndexNameSessionRepository.class);

  private final UnreadableSessionCleaner unreadable = mock(UnreadableSessionCleaner.class);
  private final SessionLookup lookup = new SessionLookup(sessions, unreadable);

  private static UnreadableSessionException unreadableValue() {
    return new UnreadableSessionException("읽지 못함(테스트)", new IllegalStateException());
  }

  private static MapSession live(String id) {
    MapSession session = new MapSession(id);
    session.setMaxInactiveInterval(Duration.ofDays(3));
    session.setLastAccessedTime(Instant.now());
    return session;
  }

  @Test
  void aSessionThatCannotBeReadIsListedWithoutAValue() {
    when(sessions.findByPrincipalName("user")).thenThrow(unreadableValue());
    when(unreadable.sessionIdsOf("user")).thenReturn(List.of("good", "broken"));
    when(sessions.findById("good")).thenReturn(live("good"));
    when(sessions.findById("broken")).thenThrow(unreadableValue());

    var found = lookup.byPrincipal("user");

    assertThat(found).containsOnlyKeys("good", "broken");
    assertThat(found.get("good")).isNotNull();
    assertThat(found.get("broken")).isNull();
  }

  @Test
  void aSessionThatCannotBeReadIsNotUsable() {
    when(sessions.findById("broken")).thenThrow(unreadableValue());
    when(sessions.findById("good")).thenReturn(live("good"));

    assertThat(lookup.isUsable("broken")).isFalse();
    assertThat(lookup.isUsable("good")).isTrue();
    assertThat(lookup.isUsable("missing")).isFalse();
  }

  @Test
  void otherStoreFailuresAreThrown() {
    when(sessions.findById("any")).thenThrow(new IllegalStateException("store down"));

    assertThatThrownBy(() -> lookup.isUsable("any")).isInstanceOf(IllegalStateException.class);
  }
}
