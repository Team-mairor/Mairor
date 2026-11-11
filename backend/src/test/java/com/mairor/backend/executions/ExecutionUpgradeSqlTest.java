package com.mairor.backend.executions;

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

/** 운영 396 스크립트를 적용한 DB에서 실제 395 SQL의 성공·전체 롤백을 확인한다. */
@Testcontainers
class ExecutionUpgradeSqlTest {
  @Container
  static final PostgreSQLContainer POSTGRES =
      new PostgreSQLContainer(DockerImageName.parse("postgres:17"));

  @Test
  void productionUpgradeCreatesExecutionTablesAndOwnershipConstraints() throws Exception {
    try (Connection connection = existingCameraSchema()) {
      upgrade(connection);
      assertThat(table(connection, "guide_executions")).isNotNull();
      assertThat(table(connection, "execution_steps")).isNotNull();
      assertThat(table(connection, "history_records")).isNotNull();
      try (var statement = connection.createStatement();
          var result =
              statement.executeQuery(
                  "select count(*) from pg_constraint where connamespace = current_schema()::regnamespace and conname in ('fk_guide_executions_face_owner', 'fk_guide_executions_match_owner_guide', 'fk_execution_steps_execution_owner', 'fk_execution_steps_photo_owner_step', 'fk_face_registrations_execution_owner')")) {
        result.next();
        assertThat(result.getInt(1)).isEqualTo(5);
      }
    }
  }

  @Test
  void laterFailureRollsBackTablesAndChangesToExistingTables() throws Exception {
    try (Connection connection = existingCameraSchema()) {
      try (var statement = connection.createStatement()) {
        statement.execute("create table execution_steps (id uuid primary key)");
      }
      assertThatThrownBy(() -> upgrade(connection))
          .isInstanceOf(ScriptStatementFailedException.class);
      try (var statement = connection.createStatement()) {
        statement.execute("rollback");
      }
      assertThat(table(connection, "guide_executions")).isNull();
      assertThat(table(connection, "execution_steps")).isNotNull();
      try (var statement = connection.createStatement();
          var result =
              statement.executeQuery(
                  "select count(*) from pg_constraint where connamespace = current_schema()::regnamespace and conname in ('uk_face_registrations_owner_session', 'uk_photos_owner_session_step', 'uk_guide_matches_owner_guide')")) {
        result.next();
        assertThat(result.getInt(1)).isZero();
      }
    }
  }

  @Test
  void existingDanglingExecutionLinkAbortsTheEntireUpgrade() throws Exception {
    try (Connection connection = existingCameraSchema()) {
      try (var statement = connection.createStatement()) {
        statement.execute("insert into users values ('00000000-0000-0000-0000-000000000001')");
        statement.execute("insert into videos values ('00000000-0000-0000-0000-000000000002')");
        statement.execute(
            "insert into photos (id, user_id, session_id, kind, storage_key, content_type, byte_size, width, height, state, created_at, updated_at) values ('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', 'session', 'FACE_REGISTRATION', 'photos/test', 'image/png', 10, 2, 2, 'AVAILABLE', now(), now())");
        statement.execute(
            "insert into face_registrations (id, user_id, session_id, video_id, photo_id, execution_id, status, lighting, distance, frontal, unobstructed, makeup_detected, notice_version, agreed_at, created_at, updated_at) values ('00000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001', 'session', '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000005', 'LINKED', true, true, true, true, false, 'v1', now(), now(), now())");
      }
      assertThatThrownBy(() -> upgrade(connection))
          .isInstanceOf(ScriptStatementFailedException.class)
          .hasMessageContaining("fk_face_registrations_execution_owner");
      try (var statement = connection.createStatement()) {
        statement.execute("rollback");
      }
      assertThat(table(connection, "guide_executions")).isNull();
      assertThat(table(connection, "execution_steps")).isNull();
      assertThat(table(connection, "face_registrations")).isNotNull();
    }
  }

  private Connection existingCameraSchema() throws SQLException {
    Connection connection =
        DriverManager.getConnection(
            POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
    String schema = "execution_" + UUID.randomUUID().toString().replace("-", "");
    try (var statement = connection.createStatement()) {
      statement.execute("create schema " + schema);
      statement.execute("set search_path to " + schema);
      statement.execute("create table users (id uuid primary key)");
      statement.execute("create table videos (id uuid primary key)");
      statement.execute("create table guides (id uuid primary key)");
      statement.execute(
          "create table guide_matches (id uuid primary key, user_id uuid not null, guide_id uuid not null)");
    }
    ScriptUtils.executeSqlScript(
        connection, new ClassPathResource("db/upgrade/396-face-registrations.sql"));
    return connection;
  }

  private void upgrade(Connection connection) {
    ScriptUtils.executeSqlScript(
        connection, new ClassPathResource("db/upgrade/395-guide-executions.sql"));
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
