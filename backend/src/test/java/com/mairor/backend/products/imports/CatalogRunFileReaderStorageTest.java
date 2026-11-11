package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.storage.LocalObjectStorage;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.products.imports.CatalogImportProperties.Source;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;

/** {@code catalog.import.source=storage}: 결과 파일을 저장소의 catalog-runs/ 에서 받아 캐시 폴더에서 읽는다. */
class CatalogRunFileReaderStorageTest {

  private static final String NAME = "20261111-070448-romand.jsonl";
  private static final String HEADER =
      "{\"runId\":\"r-1\",\"startedAt\":\"2026-11-11T07:04:48Z\",\"seed\":\"OFFICIAL:romand.co.kr\"}\n";

  @TempDir Path bucket;
  @TempDir Path cache;

  /** 받은 키를 남기는 로컬 저장소. */
  private static final class Recording extends LocalObjectStorage {
    final List<String> downloads = new ArrayList<>();

    Recording(Path root) {
      super(root);
    }

    @Override
    public void download(String key, Path target) {
      downloads.add(key);
      super.download(key, target);
    }
  }

  private CatalogRunFileReader reader(ObjectStorage storage, Duration ttl) {
    return new CatalogRunFileReader(
        new CatalogImportProperties(
            Duration.ofMinutes(10), cache, Source.STORAGE, "catalog-runs/", ttl),
        new ObjectMapper(),
        storage);
  }

  private void upload(String content) throws IOException {
    Path object = bucket.resolve("catalog-runs").resolve(NAME);
    Files.createDirectories(object.getParent());
    Files.writeString(object, content, StandardCharsets.UTF_8);
  }

  @Test
  void theFileIsDownloadedFromThePrefixIntoTheCacheAndRead() throws Exception {
    upload(HEADER + "{\"itemKey\":\"000001\"}\n");
    Recording storage = new Recording(bucket);

    Path file = reader(storage, Duration.ofMinutes(5)).resolve(NAME);

    assertThat(storage.downloads).containsExactly("catalog-runs/" + NAME);
    assertThat(file).isEqualTo(cache.resolve(NAME).toAbsolutePath().normalize());
    assertThat(reader(storage, Duration.ofMinutes(5)).header(file).runId()).isEqualTo("r-1");
    try (Stream<Path> left = Files.list(cache)) {
      assertThat(left).containsExactly(file);
    }
  }

  @Test
  void aFreshCopyIsReusedAndAnOldOneIsDownloadedAgain() throws Exception {
    upload(HEADER);
    Recording storage = new Recording(bucket);
    CatalogRunFileReader reader = reader(storage, Duration.ofMinutes(5));

    Path file = reader.resolve(NAME);
    reader.resolve(NAME);
    assertThat(storage.downloads).hasSize(1);

    upload(HEADER + "{\"itemKey\":\"000001\"}\n");
    Files.setLastModifiedTime(file, FileTime.from(Instant.now().minus(Duration.ofMinutes(6))));
    reader.resolve(NAME);

    assertThat(storage.downloads).hasSize(2);
    assertThat(Files.readString(file)).contains("000001");
  }

  @Test
  void downloadingClearsExpiredCopiesButKeepsFreshOnesAndOtherFiles() throws Exception {
    upload(HEADER);
    Path old = Files.writeString(cache.resolve("20261101-000000-old.jsonl"), HEADER);
    Path leftover = Files.writeString(cache.resolve(".x.jsonl.part"), "half");
    Path fresh = Files.writeString(cache.resolve("20261111-000000-fresh.jsonl"), HEADER);
    Path other = Files.writeString(cache.resolve("notes.txt"), "keep");
    FileTime expired = FileTime.from(Instant.now().minus(Duration.ofMinutes(10)));
    Files.setLastModifiedTime(old, expired);
    Files.setLastModifiedTime(leftover, expired);
    Files.setLastModifiedTime(other, expired);

    reader(new Recording(bucket), Duration.ofMinutes(5)).resolve(NAME);

    assertThat(old).doesNotExist();
    assertThat(leftover).doesNotExist();
    assertThat(fresh).exists();
    assertThat(other).exists();
    assertThat(cache.resolve(NAME)).exists();
  }

  @Test
  void aMissingObjectIsNotFound() {
    assertThatThrownBy(() -> reader(new Recording(bucket), Duration.ofMinutes(5)).resolve(NAME))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.code()).isEqualTo(CatalogRunFileReader.FILE_NOT_FOUND));
  }

  @Test
  void anUnreachableStorageIsUnavailableAndLeavesNoPartFile() throws Exception {
    ObjectStorage down =
        new LocalObjectStorage(bucket) {
          @Override
          public void download(String key, Path target) {
            try {
              Files.writeString(target, "half");
            } catch (IOException e) {
              throw new IllegalStateException(e);
            }
            throw new StorageException("닿지 못함", null);
          }
        };

    assertThatThrownBy(() -> reader(down, Duration.ofMinutes(5)).resolve(NAME))
        .isInstanceOfSatisfying(
            BusinessException.class, e -> assertThat(e.code()).isEqualTo("SERVICE_UNAVAILABLE"));
    try (Stream<Path> left = Files.list(cache)) {
      assertThat(left).isEmpty();
    }
  }

  @Test
  void badNamesAreRejectedBeforeAnythingIsDownloaded() {
    Recording storage = new Recording(bucket);

    assertThatThrownBy(() -> reader(storage, Duration.ofMinutes(5)).resolve("../x.jsonl"))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.code()).isEqualTo(CatalogRunFileReader.INVALID_FILE));
    assertThat(storage.downloads).isEmpty();
  }
}
