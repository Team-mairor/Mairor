package com.mairor.backend.camera;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.testcontainers.images.builder.Transferable;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class CameraDeployPreflightTest {
  @Container
  static final PostgreSQLContainer POSTGRES =
      new PostgreSQLContainer(DockerImageName.parse("postgres:17"));

  @Test
  void deploymentStopsBeforeMigrationAndWithMissingIndexButAcceptsTheAppliedSchema()
      throws Exception {
    POSTGRES.copyFileToContainer(
        Transferable.of(Files.readAllBytes(Path.of("..", "deploy", "check-camera-schema.sql"))),
        "/tmp/check.sql");
    try (var connection =
            DriverManager.getConnection(
                POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
        var statement = connection.createStatement()) {
      assertThat(preflight()).isNotZero();
      statement.execute("create table users (id uuid primary key)");
      statement.execute("create table videos (id uuid primary key)");
      statement.execute("create table guides (id uuid primary key)");
      ScriptUtils.executeSqlScript(
          connection, new ClassPathResource("db/upgrade/396-face-registrations.sql"));
      assertThat(preflight()).isZero();
      statement.execute("drop index uk_face_registrations_registered");
      assertThat(preflight()).isNotZero();
    }
  }

  private int preflight() throws Exception {
    return POSTGRES
        .execInContainer(
            "psql",
            "-U",
            POSTGRES.getUsername(),
            "-d",
            POSTGRES.getDatabaseName(),
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            "/tmp/check.sql")
        .getExitCode();
  }
}
