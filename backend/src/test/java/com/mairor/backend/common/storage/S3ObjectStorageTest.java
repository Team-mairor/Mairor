package com.mairor.backend.common.storage;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import software.amazon.awssdk.services.s3.model.S3Exception;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

/** 사전 서명은 네트워크 없이 계산만 한다. 시험용 자격 증명으로 주소 모양만 본다. */
class S3ObjectStorageTest {

  @Test
  void deletesTheExactKeyAndTreatsMissingObjectsAsSuccess() {
    S3Client client = mock(S3Client.class);
    S3ObjectStorage storage = new S3ObjectStorage(client, mock(S3Presigner.class), "private-media");
    storage.delete("photos/one");
    verify(client)
        .deleteObject(
            DeleteObjectRequest.builder().bucket("private-media").key("photos/one").build());
    when(client.deleteObject(any(DeleteObjectRequest.class)))
        .thenThrow(NoSuchKeyException.builder().message("missing").build());
    storage.delete("photos/one");
  }

  @Test
  void deleteFailuresRemainRetryableStorageFailures() {
    S3Client client = mock(S3Client.class);
    S3ObjectStorage storage = new S3ObjectStorage(client, mock(S3Presigner.class), "private-media");
    when(client.deleteObject(any(DeleteObjectRequest.class)))
        .thenThrow(S3Exception.builder().statusCode(503).message("unavailable").build());
    assertThatThrownBy(() -> storage.delete("photos/one")).isInstanceOf(StorageException.class);
  }

  @Test
  void presignedUrlPointsToTheKeyAndCarriesTheExpiry() {
    StaticCredentialsProvider credentials =
        StaticCredentialsProvider.create(AwsBasicCredentials.create("AKIATESTTEST", "secret"));
    Region region = Region.AP_NORTHEAST_2;
    try (S3ObjectStorage storage =
        new S3ObjectStorage(
            S3Client.builder().region(region).credentialsProvider(credentials).build(),
            S3Presigner.builder().region(region).credentialsProvider(credentials).build(),
            "mairor-test-media")) {

      URI url = storage.presignGet("videos/VxAXD6PP76I/frames/000030.jpg", Duration.ofHours(24));

      assertThat(url.getScheme()).isEqualTo("https");
      assertThat(url.toString())
          .contains("mairor-test-media")
          .contains("videos/VxAXD6PP76I/frames/000030.jpg")
          .contains("X-Amz-Expires=86400")
          .contains("X-Amz-Signature=");
    }
  }
}
