package com.mairor.backend.analysis.worker;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class WorkDirCleanerTest {

  @TempDir Path workDir;

  @Test
  void leftoverJobFoldersAreRemovedButTheWorkDirStays() throws IOException {
    Path job = Files.createDirectories(workDir.resolve("job-1/frames"));
    Files.writeString(job.resolve("000001.jpg"), "frame");
    Files.writeString(workDir.resolve("job-2.mp4"), "video");

    int removed = WorkDirCleaner.clear(workDir);

    assertThat(removed).isEqualTo(2);
    assertThat(workDir).isEmptyDirectory();
  }

  @Test
  void aMissingWorkDirIsNothingToDo() {
    assertThat(WorkDirCleaner.clear(workDir.resolve("none"))).isZero();
  }
}
