package com.mairor.backend.camera;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ScriptStatementFailedException;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/** 운영 파일을 그대로 실행해 CREATE/FK와 전체 트랜잭션의 실패 롤백을 확인한다. */
@Testcontainers
class CameraUpgradeSqlTest {
  @Container
  static final PostgreSQLContainer POSTGRES =
      new PostgreSQLContainer(DockerImageName.parse("postgres:17"));

  @Test
  void productionUpgradeCreatesBothTablesAndNamedConstraints() throws Exception {
    try (Connection connection = freshSchema()) {
      upgrade(connection);
      assertThat(table(connection, "photos")).isNotNull();
      assertThat(table(connection, "face_registrations")).isNotNull();
      try (var statement = connection.createStatement();
          var result =
              statement.executeQuery(
                  """
              select count(*) from pg_constraint
              where conrelid = 'face_registrations'::regclass
                and conname in ('fk_face_registrations_photo_owner',
                  'ck_face_registrations_status', 'uk_face_registrations_execution')
              """)) {
        result.next();
        assertThat(result.getInt(1)).isEqualTo(3);
      }
      try (var statement = connection.createStatement();
          var result =
              statement.executeQuery(
                  """
              select count(*) from pg_indexes where schemaname = current_schema()
                and indexname = 'uk_face_registrations_registered'
                and indexdef like '%WHERE%'
              """)) {
        result.next();
        assertThat(result.getInt(1)).isEqualTo(1);
      }
    }
  }

  @Test
  void laterCreateFailureRollsBackTheEarlierPhotosTable() throws Exception {
    try (Connection connection = freshSchema()) {
      try (var statement = connection.createStatement()) {
        statement.execute("create table face_registrations (id uuid primary key)");
      }
      assertThatThrownBy(() -> upgrade(connection))
          .isInstanceOf(ScriptStatementFailedException.class);
      try (var statement = connection.createStatement()) {
        statement.execute("rollback");
      }
      assertThat(table(connection, "photos")).isNull();
      assertThat(table(connection, "face_registrations")).isNotNull();
    }
  }

  private Connection freshSchema() throws SQLException {
    Connection connection =
        DriverManager.getConnection(
            POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
    String schema = "camera_" + UUID.randomUUID().toString().replace("-", "");
    try (var statement = connection.createStatement()) {
      statement.execute("create schema " + schema);
      statement.execute("set search_path to " + schema);
      statement.execute("create table users (id uuid primary key)");
      statement.execute("create table videos (id uuid primary key)");
      statement.execute("create table guides (id uuid primary key)");
    }
    return connection;
  }

  private void upgrade(Connection connection) {
    ScriptUtils.executeSqlScript(
        connection, new ClassPathResource("db/upgrade/396-face-registrations.sql"));
  }

  private String table(Connection connection, String name) throws SQLException {
    try (var statement = connection.prepareStatement("select to_regclass(?)::text")) {
      statement.setString(1, name);
      try (var result = statement.executeQuery()) {
        result.next();
        return result.getString(1);
      }
    }
  }
}
