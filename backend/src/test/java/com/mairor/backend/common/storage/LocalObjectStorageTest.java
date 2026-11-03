package com.mairor.backend.common.storage;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LocalObjectStorageTest {

  @TempDir Path root;
  @TempDir Path work;

  @Test
  void downloadsAnObjectUnderTheRoot() throws IOException {
    Path source = root.resolve("videos/abc/source.mp4");
    Files.createDirectories(source.getParent());
    Files.writeString(source, "video");
    LocalObjectStorage storage = new LocalObjectStorage(root);
    Path target = work.resolve("job/source.mp4");

    storage.download("videos/abc/source.mp4", target);

    assertThat(target).hasContent("video");
    assertThat(storage.exists("videos/abc/source.mp4")).isTrue();
  }

  @Test
  void missingObjectIsNotFound() {
    LocalObjectStorage storage = new LocalObjectStorage(root);

    assertThatThrownBy(() -> storage.download("videos/none.mp4", work.resolve("x.mp4")))
        .isInstanceOf(ObjectNotFoundException.class);
    assertThat(storage.exists("videos/none.mp4")).isFalse();
  }

  @Test
  void uploadsAndGivesAFileUri() throws IOException {
    Path source = Files.writeString(work.resolve("000030.jpg"), "jpeg");
    LocalObjectStorage storage = new LocalObjectStorage(root);

    storage.upload(source, "videos/abc/frames/000030.jpg", "image/jpeg");

    assertThat(root.resolve("videos/abc/frames/000030.jpg")).hasContent("jpeg");
    assertThat(storage.presignGet("videos/abc/frames/000030.jpg", java.time.Duration.ofHours(24)))
        .isEqualTo(root.resolve("videos/abc/frames/000030.jpg").toUri());
  }

  @Test
  void keyOutsideTheRootIsRejected() {
    LocalObjectStorage storage = new LocalObjectStorage(root);

    assertThatThrownBy(() -> storage.exists("../secret.txt"))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
