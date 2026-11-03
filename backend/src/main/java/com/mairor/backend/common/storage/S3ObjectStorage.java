package com.mairor.backend.common.storage;

import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

/**
 * S3 버킷을 저장소로 쓴다(운영). 자격 증명은 AWS 기본 공급자 체인이라 운영 EC2 에서는 인스턴스 역할(-203 `mairor-ec2-app`의 S3 권한)을 쓴다.
 */
public class S3ObjectStorage implements ObjectStorage, AutoCloseable {

  private final S3Client client;
  private final S3Presigner presigner;
  private final String bucket;

  public S3ObjectStorage(S3Client client, S3Presigner presigner, String bucket) {
    this.client = client;
    this.presigner = presigner;
    this.bucket = bucket;
  }

  @Override
  public void download(String key, Path target) {
    try {
      if (target.getParent() != null) {
        Files.createDirectories(target.getParent());
      }
      // toFile 은 대상 파일이 있으면 실패하므로 먼저 지운다
      Files.deleteIfExists(target);
      client.getObject(GetObjectRequest.builder().bucket(bucket).key(key).build(), target);
    } catch (NoSuchKeyException e) {
      throw new ObjectNotFoundException(key);
    } catch (SdkException | IOException e) {
      throw new StorageException("S3 에서 내려받지 못했습니다: " + key, e);
    }
  }

  @Override
  public boolean exists(String key) {
    try {
      client.headObject(HeadObjectRequest.builder().bucket(bucket).key(key).build());
      return true;
    } catch (NoSuchKeyException e) {
      return false;
    } catch (SdkException e) {
      throw new StorageException("S3 객체를 확인하지 못했습니다: " + key, e);
    }
  }

  @Override
  public void upload(Path source, String key, String contentType) {
    try {
      client.putObject(
          PutObjectRequest.builder().bucket(bucket).key(key).contentType(contentType).build(),
          RequestBody.fromFile(source));
    } catch (SdkException e) {
      throw new StorageException("S3 에 올리지 못했습니다: " + key, e);
    }
  }

  @Override
  public URI presignGet(String key, Duration ttl) {
    try {
      return presigner
          .presignGetObject(
              GetObjectPresignRequest.builder()
                  .signatureDuration(ttl)
                  .getObjectRequest(r -> r.bucket(bucket).key(key))
                  .build())
          .url()
          .toURI();
    } catch (SdkException | URISyntaxException e) {
      throw new StorageException("사전 서명 URL 을 만들지 못했습니다: " + key, e);
    }
  }

  @Override
  public void close() {
    presigner.close();
    client.close();
  }
}
