package com.mairor.backend.users.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 스키마 SQL({@code db/schema/users.sql})이 {@link User} 엔티티와 맞는지 확인한다.
 *
 * <p>운영과 같은 조건이다. 테이블이 없는 새 DB에 SQL 을 먼저 적용하고, {@code ddl-auto=validate} 로 앱을 띄운다. 엔티티를 바꾸고 SQL 을
 * 고치지 않으면 앱이 뜨지 않아 이 테스트가 실패한다. 다른 테스트는 {@code dev} 의 {@code ddl-auto=update} 로 테이블을 만들기 때문에 이런
 * 어긋남을 못 잡는다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class UsersSchemaSqlTest {

  @Autowired private JdbcTemplate jdbc;

  @Test
  void entityValidatesAgainstTheSqlSchema() {
    // 앱이 ddl-auto=validate 로 기동했다는 것 자체가 엔티티와 SQL 이 맞다는 뜻이다
    assertThat(jdbc.queryForObject("select count(*) from users", Integer.class)).isZero();
  }

  @Test
  void columnsHaveTheExpectedNullabilityAndLength() {
    List<Map<String, Object>> columns =
        jdbc.queryForList(
            "select column_name, is_nullable, character_maximum_length "
                + "from information_schema.columns where table_name = 'users'");

    assertThat(columns)
        .extracting(c -> c.get("column_name"))
        .containsExactlyInAnyOrder(
            "id",
            "email",
            "password_hash",
            "provider",
            "nickname",
            "name",
            "phone",
            "birth_date",
            "gender",
            "email_verified_at",
            "created_at",
            "updated_at");
    assertThat(column(columns, "password_hash").get("is_nullable")).isEqualTo("YES");
    assertThat(column(columns, "email").get("is_nullable")).isEqualTo("NO");
    assertThat(column(columns, "email").get("character_maximum_length")).isEqualTo(254);
    assertThat(column(columns, "password_hash").get("character_maximum_length")).isEqualTo(255);

    // 가입 때 선택으로 받는 프로필은 비어 있을 수 있고, provider 는 항상 있다
    assertThat(column(columns, "provider").get("is_nullable")).isEqualTo("NO");
    for (String optional :
        List.of("nickname", "name", "phone", "birth_date", "gender", "email_verified_at")) {
      assertThat(column(columns, optional).get("is_nullable")).as(optional).isEqualTo("YES");
    }
    assertThat(column(columns, "provider").get("character_maximum_length")).isEqualTo(10);
    assertThat(column(columns, "nickname").get("character_maximum_length")).isEqualTo(20);
    assertThat(column(columns, "name").get("character_maximum_length")).isEqualTo(50);
    assertThat(column(columns, "phone").get("character_maximum_length")).isEqualTo(11);
    assertThat(column(columns, "gender").get("character_maximum_length")).isEqualTo(10);
  }

  @Test
  void constraintsUseTheNamesTheCodeDependsOn() {
    List<String> names =
        jdbc.queryForList(
            "select conname from pg_constraint where conrelid = 'users'::regclass", String.class);

    assertThat(names).contains("users_pkey", User.EMAIL_UNIQUE);
  }

  @Test
  void duplicateEmailViolatesTheNamedUniqueConstraint() {
    String insert =
        "insert into users (id, email, provider, created_at, updated_at) "
            + "values (gen_random_uuid(), ?, 'LOCAL', now(), now())";
    jdbc.update(insert, "member@example.com");

    assertThatThrownBy(() -> jdbc.update(insert, "member@example.com"))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(User.EMAIL_UNIQUE);
  }

  @Test
  void userAgreementsColumnsAndConstraintsMatchTheEntity() {
    List<Map<String, Object>> columns =
        jdbc.queryForList(
            "select column_name, is_nullable, character_maximum_length "
                + "from information_schema.columns where table_name = 'user_agreements'");

    assertThat(columns)
        .extracting(c -> c.get("column_name"))
        .containsExactlyInAnyOrder("id", "user_id", "type", "version", "agreed", "agreed_at");
    for (Map<String, Object> c : columns) {
      assertThat(c.get("is_nullable")).as(String.valueOf(c.get("column_name"))).isEqualTo("NO");
    }
    assertThat(column(columns, "type").get("character_maximum_length")).isEqualTo(30);
    assertThat(column(columns, "version").get("character_maximum_length")).isEqualTo(20);

    List<String> names =
        jdbc.queryForList(
            "select conname from pg_constraint where conrelid = 'user_agreements'::regclass",
            String.class);
    assertThat(names)
        .contains("user_agreements_pkey", UserAgreement.USER_FK, UserAgreement.USER_TYPE_UNIQUE);
  }

  @Test
  void sameAgreementTypeTwiceForOneUserViolatesTheUniqueConstraint() {
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at) "
            + "values ('00000000-0000-0000-0000-000000000001', 'a@example.com', 'LOCAL', now(), now())");
    String insert =
        "insert into user_agreements (id, user_id, type, version, agreed, agreed_at) "
            + "values (gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'TERMS', 'v1', true, now())";
    jdbc.update(insert);

    assertThatThrownBy(() -> jdbc.update(insert))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(UserAgreement.USER_TYPE_UNIQUE);
  }

  @Test
  void agreementsMustReferenceAnExistingUser() {
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "insert into user_agreements (id, user_id, type, version, agreed, agreed_at) "
                        + "values (gen_random_uuid(), gen_random_uuid(), 'TERMS', 'v1', true, now())"))
        .hasMessageContaining(UserAgreement.USER_FK);
  }

  private static Map<String, Object> column(List<Map<String, Object>> columns, String name) {
    return columns.stream()
        .filter(c -> name.equals(c.get("column_name")))
        .findFirst()
        .orElseThrow();
  }
}
