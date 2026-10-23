package com.mairor.backend;

import org.springframework.boot.SpringApplication;

/** {@code ./gradlew bootTestRun} 으로 compose 없이 Testcontainers DB 위에서 서버를 띄운다. */
public class TestBackendApplication {

  public static void main(String[] args) {
    SpringApplication.from(BackendApplication::main)
        .with(TestcontainersConfiguration.class)
        .run(args);
  }
}
