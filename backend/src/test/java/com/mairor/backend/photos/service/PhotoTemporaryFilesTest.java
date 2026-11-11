package com.mairor.backend.photos.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class PhotoTemporaryFilesTest {
  @TempDir Path directory;
  private final Instant now = Instant.parse("2026-11-10T00:00:00Z");

  @Test
  void removesOnlyOldAbandonedUploadFiles() throws Exception {
    PhotoTemporaryFiles files =
        new PhotoTemporaryFiles(directory, Clock.fixed(now, ZoneOffset.UTC));
    Path old = Files.writeString(directory.resolve("photo-old.upload"), "old");
    Path recent = Files.writeString(directory.resolve("photo-new.upload"), "new");
    Path unrelated = Files.writeString(directory.resolve("other.txt"), "keep");
    Files.setLastModifiedTime(old, FileTime.from(now.minusSeconds(7200)));
    Files.setLastModifiedTime(recent, FileTime.from(now));
    Files.setLastModifiedTime(unrelated, FileTime.from(now.minusSeconds(7200)));
    files.sweep();
    assertThat(old).doesNotExist();
    assertThat(recent).exists();
    assertThat(unrelated).exists();
  }

  @Test
  void protectsActiveUploadEvenWhenItsTimestampIsOld() throws Exception {
    PhotoTemporaryFiles files =
        new PhotoTemporaryFiles(directory, Clock.fixed(now, ZoneOffset.UTC));
    try (var lease = files.create()) {
      Files.setLastModifiedTime(lease.path(), FileTime.from(now.minusSeconds(7200)));
      files.sweep();
      assertThat(lease.path()).exists();
    }
    try (var paths = Files.list(directory)) {
      assertThat(paths.toList()).isEmpty();
    }
  }
}
