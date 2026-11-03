package com.mairor.backend.common.storage;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

/** {@code app.storage.type}에 맞는 {@link ObjectStorage}를 만든다. S3 클라이언트는 S3 를 고를 때만 만든다. */
@Configuration
class StorageConfig {

  @Bean
  ObjectStorage objectStorage(StorageProperties properties) {
    return switch (properties.type()) {
      case LOCAL -> new LocalObjectStorage(properties.local().root());
      case S3 -> {
        String bucket = properties.s3().bucket();
        if (bucket == null || bucket.isBlank()) {
          throw new IllegalStateException("app.storage.s3.bucket 을 설정해야 합니다.");
        }
        S3Client client = S3Client.builder().region(Region.of(properties.s3().region())).build();
        yield new S3ObjectStorage(client, bucket);
      }
    };
  }
}
