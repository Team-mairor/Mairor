package com.mairor.backend.users.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.entity.User;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.transaction.annotation.Transactional;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@Transactional
class UserRepositoryTest {

  @Autowired private UserRepository userRepository;

  @Test
  void save_generatesIdAndTimestamps() {
    User saved = userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}hash"));

    assertThat(saved.getId()).isNotNull();
    assertThat(saved.getCreatedAt()).isNotNull();
    assertThat(saved.getUpdatedAt()).isNotNull();
    assertThat(saved.getPasswordHash()).isEqualTo("{bcrypt}hash");
  }

  @Test
  void save_allowsMissingPasswordHash() {
    User saved = userRepository.saveAndFlush(new User("google-only@example.com", null));

    assertThat(userRepository.findById(saved.getId()))
        .get()
        .extracting(User::getPasswordHash)
        .isNull();
  }

  @Test
  void existsByEmail_matchesStoredEmail() {
    userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}hash"));

    assertThat(userRepository.existsByEmail("member@example.com")).isTrue();
    assertThat(userRepository.existsByEmail("other@example.com")).isFalse();
  }

  @Test
  void newUserStartsAtPasswordVersionZero() {
    User saved = userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}hash"));

    assertThat(userRepository.findById(saved.getId()).orElseThrow().getPasswordVersion()).isZero();
  }

  @Test
  void updatePassword_replacesTheHashAndRaisesTheVersionByOne() {
    User saved = userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}old"));
    Instant changedAt = Instant.parse("2030-01-02T03:04:05Z");

    int updated = userRepository.updatePassword(saved.getId(), "{bcrypt}new", changedAt);

    assertThat(updated).isEqualTo(1);
    User reloaded = userRepository.findById(saved.getId()).orElseThrow();
    assertThat(reloaded.getPasswordHash()).isEqualTo("{bcrypt}new");
    assertThat(reloaded.getPasswordVersion()).isEqualTo(1);
    assertThat(reloaded.getUpdatedAt()).isEqualTo(changedAt);
  }

  @Test
  void updatePassword_raisesTheVersionEveryTime() {
    User saved = userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}old"));

    userRepository.updatePassword(saved.getId(), "{bcrypt}one", Instant.now());
    userRepository.updatePassword(saved.getId(), "{bcrypt}two", Instant.now());

    User reloaded = userRepository.findById(saved.getId()).orElseThrow();
    assertThat(reloaded.getPasswordHash()).isEqualTo("{bcrypt}two");
    assertThat(reloaded.getPasswordVersion()).isEqualTo(2);
  }

  @Test
  void updatePassword_leavesOtherUsersAlone() {
    User target = userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}old"));
    User other = userRepository.saveAndFlush(new User("other@example.com", "{bcrypt}other"));

    userRepository.updatePassword(target.getId(), "{bcrypt}new", Instant.now());

    User untouched = userRepository.findById(other.getId()).orElseThrow();
    assertThat(untouched.getPasswordHash()).isEqualTo("{bcrypt}other");
    assertThat(untouched.getPasswordVersion()).isZero();
  }

  @Test
  void updatePassword_forAnUnknownUserChangesNothing() {
    assertThat(userRepository.updatePassword(UUID.randomUUID(), "{bcrypt}new", Instant.now()))
        .isZero();
  }

  @Test
  void updatePassword_givesAGoogleOnlyUserAHash() {
    User saved = userRepository.saveAndFlush(new User("google-only@example.com", null));

    userRepository.updatePassword(saved.getId(), "{bcrypt}new", Instant.now());

    assertThat(userRepository.findById(saved.getId()).orElseThrow().getPasswordHash())
        .isEqualTo("{bcrypt}new");
  }

  @Test
  void save_duplicateEmail_violatesNamedUniqueConstraint() {
    userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}hash"));

    assertThatThrownBy(
            () -> userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}other")))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(User.EMAIL_UNIQUE);
  }
}
