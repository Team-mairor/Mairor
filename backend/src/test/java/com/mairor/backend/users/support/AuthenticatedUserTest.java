package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.AuthenticatedPrincipal;

class AuthenticatedUserTest {

  private static final UUID USER_ID = UUID.fromString("3f2b8c1e-5a7d-4e6f-9b0a-1c2d3e4f5a6b");

  @Test
  void nameIsTheUserIdSoTheSessionIndexIsStable() {
    AuthenticatedUser user = new AuthenticatedUser(USER_ID, "member@example.com");

    assertThat(user).isInstanceOf(AuthenticatedPrincipal.class);
    assertThat(user.getName()).isEqualTo(USER_ID.toString());
  }

  @Test
  void nameDoesNotChangeWhenTheEmailDiffers() {
    AuthenticatedUser first = new AuthenticatedUser(USER_ID, "old@example.com");
    AuthenticatedUser second = new AuthenticatedUser(USER_ID, "new@example.com");

    assertThat(first.getName()).isEqualTo(second.getName());
  }

  @Test
  void survivesJavaSerializationAsTheJdbcSessionStoreNeeds() throws Exception {
    AuthenticatedUser user = new AuthenticatedUser(USER_ID, "member@example.com");

    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
      out.writeObject(user);
    }
    Object restored;
    try (ObjectInputStream in =
        new ObjectInputStream(new ByteArrayInputStream(bytes.toByteArray()))) {
      restored = in.readObject();
    }

    assertThat(restored).isEqualTo(user);
    assertThat(((AuthenticatedUser) restored).getName()).isEqualTo(USER_ID.toString());
  }

  @Test
  void toStringDoesNotExposeTheEmail() {
    AuthenticatedUser user = new AuthenticatedUser(USER_ID, "member@example.com");

    assertThat(user.toString()).contains(USER_ID.toString()).doesNotContain("member@example.com");
  }

  @Test
  void rejectsMissingValues() {
    assertThatThrownBy(() -> new AuthenticatedUser(null, "member@example.com"))
        .isInstanceOf(NullPointerException.class);
    assertThatThrownBy(() -> new AuthenticatedUser(USER_ID, null))
        .isInstanceOf(NullPointerException.class);
  }
}
