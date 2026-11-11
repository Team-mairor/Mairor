package com.mairor.backend.pouch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.pouch.service.PouchDeletionService;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 내 파우치 삭제 API의 소유권·인증·CSRF·버전 원자성을 PostgreSQL로 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@AutoConfigureMockMvc
class PouchDeletionApiTest {

  private static final String PATH = "/v1/users/me/pouch-items";

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private PouchDeletionService deletionService;
  @Autowired private PlatformTransactionManager transactionManager;

  private UUID userId;
  private UUID otherUserId;
  private UUID itemId;
  private UUID otherItemId;
  private String category;
  private String type;

  @BeforeEach
  void setUp() {
    userId = UUID.randomUUID();
    otherUserId = UUID.randomUUID();
    itemId = UUID.randomUUID();
    otherItemId = UUID.randomUUID();
    String suffix = UUID.randomUUID().toString().replace("-", "").substring(0, 8).toUpperCase();
    category = "PUD" + suffix;
    type = category + "_TYPE";

    for (UUID id : List.of(userId, otherUserId)) {
      jdbc.update(
          "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
          id,
          id + "@example.com");
    }
    jdbc.update("insert into product_categories values (?, '시험 분류', true, true, 1)", category);
    jdbc.update("insert into product_types values (?, ?, '시험 종류', 1)", type, category);
    insertItem(itemId, userId, "My Item");
    insertItem(otherItemId, otherUserId, "Other Item");
  }

  @AfterEach
  void cleanUp() {
    jdbc.update("delete from pouch_items where user_id in (?, ?)", userId, otherUserId);
    jdbc.update("delete from product_types where code = ?", type);
    jdbc.update("delete from product_categories where code = ?", category);
    jdbc.update("delete from users where id in (?, ?)", userId, otherUserId);
  }

  @Test
  void deletingOwnedItemReturnsNoContentAndIncrementsVersion() throws Exception {
    mockMvc
        .perform(delete(PATH + "/" + itemId).with(asMember(userId)).with(csrf()))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));

    assertThat(itemCount(userId)).isZero();
    assertThat(version(userId)).isEqualTo(1L);
  }

  @Test
  void anotherMembersAndMissingItemsReturnSameNotFoundWithoutChanges() throws Exception {
    mockMvc
        .perform(delete(PATH + "/" + otherItemId).with(asMember(userId)).with(csrf()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));

    mockMvc
        .perform(delete(PATH + "/" + UUID.randomUUID()).with(asMember(userId)).with(csrf()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));

    assertThat(itemCount(otherUserId)).isEqualTo(1);
    assertThat(version(userId)).isZero();
    assertThat(version(otherUserId)).isZero();
  }

  @Test
  void deletedItemCannotBeDeletedAgain() throws Exception {
    mockMvc
        .perform(delete(PATH + "/" + itemId).with(asMember(userId)).with(csrf()))
        .andExpect(status().isNoContent());

    mockMvc
        .perform(delete(PATH + "/" + itemId).with(asMember(userId)).with(csrf()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));

    assertThat(version(userId)).isEqualTo(1L);
  }

  @Test
  void authenticationAndCsrfAreRequired() throws Exception {
    mockMvc
        .perform(delete(PATH + "/" + itemId).with(csrf()))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));

    mockMvc
        .perform(delete(PATH + "/" + itemId).with(asMember(userId)))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));

    assertThat(itemCount(userId)).isEqualTo(1);
    assertThat(version(userId)).isZero();
  }

  @Test
  void malformedItemIdReturnsBadRequest() throws Exception {
    mockMvc
        .perform(delete(PATH + "/not-a-uuid").with(asMember(userId)).with(csrf()))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void deletionAndVersionIncrementRollBackTogether() {
    TransactionTemplate transaction = new TransactionTemplate(transactionManager);

    assertThatThrownBy(
            () ->
                transaction.executeWithoutResult(
                    status -> {
                      deletionService.delete(userId, itemId);
                      throw new IllegalStateException("rollback probe");
                    }))
        .hasMessage("rollback probe");

    assertThat(itemCount(userId)).isEqualTo(1);
    assertThat(version(userId)).isZero();
  }

  private void insertItem(UUID id, UUID owner, String name) {
    jdbc.update(
        "insert into pouch_items (id, user_id, registration_mode, category_code, type_code, brand, name, brand_normalized, name_normalized, shade_name_normalized, created_at, updated_at) values (?, ?, 'MANUAL', ?, ?, 'Brand', ?, 'brand', ?, '', now(), now())",
        id,
        owner,
        category,
        type,
        name,
        name.toLowerCase());
  }

  private int itemCount(UUID owner) {
    return jdbc.queryForObject(
        "select count(*) from pouch_items where user_id = ?", Integer.class, owner);
  }

  private long version(UUID owner) {
    return jdbc.queryForObject("select pouch_version from users where id = ?", Long.class, owner);
  }

  private static RequestPostProcessor asMember(UUID id) {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(id, "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }
}
