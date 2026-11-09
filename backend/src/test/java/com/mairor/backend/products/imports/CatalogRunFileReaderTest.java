package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.products.imports.CatalogRunFileReader.Header;
import com.mairor.backend.products.imports.CatalogRunFileReader.Line;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;

class CatalogRunFileReaderTest {

  @TempDir Path directory;

  private CatalogRunFileReader reader;

  @BeforeEach
  void setUp() {
    reader =
        new CatalogRunFileReader(
            new CatalogImportProperties(Duration.ofMinutes(10), directory), new ObjectMapper());
  }

  private Path write(String name, String content) throws IOException {
    Path file = directory.resolve(name);
    Files.writeString(file, content, StandardCharsets.UTF_8);
    return file;
  }

  private static final String HEADER =
      "{\"runId\":\"r-1\",\"startedAt\":\"2026-11-08T21:30:00+09:00\","
          + "\"seed\":\"OFFICIAL:etude.com\",\"collectorVersion\":\"0.1.0\"}\n";

  // --- 이름 ---

  @Test
  void onlyPlainRelativeJsonlNamesAreAccepted() throws Exception {
    write("20261108-213000-etude.jsonl", HEADER);

    assertThat(reader.resolve("20261108-213000-etude.jsonl")).exists();
    for (String bad :
        new String[] {
          "../a.jsonl",
          "a/b.jsonl",
          "a\\b.jsonl",
          "a.txt",
          "",
          " ",
          ".hidden.jsonl",
          "..",
          "a.jsonl/"
        }) {
      assertThatThrownBy(() -> reader.resolve(bad))
          .as(bad)
          .isInstanceOfSatisfying(
              BusinessException.class,
              e -> assertThat(e.code()).isEqualTo(CatalogRunFileReader.INVALID_FILE));
    }
    assertThatThrownBy(() -> reader.resolve(null)).isInstanceOf(BusinessException.class);
  }

  @Test
  void aMissingFileIsNotFoundWithItsOwnCode() {
    assertThatThrownBy(() -> reader.resolve("gone.jsonl"))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> {
              assertThat(e.code()).isEqualTo(CatalogRunFileReader.FILE_NOT_FOUND);
              assertThat(e.status().value()).isEqualTo(404);
            });
  }

  @Test
  void aDirectoryWithAJsonlNameIsNotAFile() throws Exception {
    Files.createDirectory(directory.resolve("dir.jsonl"));

    assertThatThrownBy(() -> reader.resolve("dir.jsonl")).isInstanceOf(BusinessException.class);
  }

  // --- header ---

  @Test
  void theHeaderIsReadFromTheFirstLine() throws Exception {
    Path file = write("a.jsonl", HEADER + "{\"itemKey\":\"000001\"}\n");

    Header header = reader.header(file);

    assertThat(header.runId()).isEqualTo("r-1");
    assertThat(header.startedAt()).isEqualTo(Instant.parse("2026-11-08T12:30:00Z"));
    assertThat(header.seed()).isEqualTo("OFFICIAL:etude.com");
    assertThat(header.collectorVersion()).isEqualTo("0.1.0");
  }

  @Test
  void optionalHeaderValuesMayBeMissingOrBadButRunIdIsRequired() throws Exception {
    Header loose =
        reader.header(write("b.jsonl", "{\"runId\":\"r-2\",\"startedAt\":\"yesterday\"}\n"));

    assertThat(loose.startedAt()).isNull();
    assertThat(loose.seed()).isNull();
    for (String content : new String[] {"", "not json\n", "[]\n", "{\"runId\":\" \"}\n", "{}\n"}) {
      Path file = write("c.jsonl", content);
      assertThatThrownBy(() -> reader.header(file))
          .as(content)
          .isInstanceOfSatisfying(
              BusinessException.class,
              e -> assertThat(e.code()).isEqualTo(CatalogRunFileReader.INVALID_FILE));
    }
  }

  // --- 줄 ---

  @Test
  void linesAfterTheHeaderAreVisitedWithTheirNumbersAndBlankLinesAreSkipped() throws Exception {
    Path file = write("d.jsonl", HEADER + "{\"itemKey\":\"000001\"}\n\n{\"itemKey\":\"000002\"}\n");
    List<Line> seen = new ArrayList<>();

    boolean finished = reader.forEachLine(file, seen::add);

    assertThat(finished).isTrue();
    assertThat(seen).extracting(Line::number).containsExactly(2, 4);
    assertThat(seen.get(1).node().path("itemKey").asString()).isEqualTo("000002");
  }

  @Test
  void aBrokenMiddleLineIsReportedAsUnreadableAndReadingContinues() throws Exception {
    Path file =
        write("e.jsonl", HEADER + "{\"itemKey\":\"1\"}\n{ broken\n[1]\n{\"itemKey\":\"2\"}\n");
    List<Line> seen = new ArrayList<>();

    reader.forEachLine(file, seen::add);

    assertThat(seen).extracting(l -> l.node() == null).containsExactly(false, true, true, false);
  }

  @Test
  void aCutOffLastLineIsIgnoredButACompleteLastLineWithoutNewlineIsKept() throws Exception {
    Path cut = write("f.jsonl", HEADER + "{\"itemKey\":\"1\"}\n{\"itemKey\":\"2\",\"colle");
    Path complete = write("g.jsonl", HEADER + "{\"itemKey\":\"1\"}\n{\"itemKey\":\"2\"}");
    List<Line> cutSeen = new ArrayList<>();
    List<Line> completeSeen = new ArrayList<>();

    reader.forEachLine(cut, cutSeen::add);
    reader.forEachLine(complete, completeSeen::add);

    assertThat(cutSeen).hasSize(1);
    assertThat(completeSeen).hasSize(2);
  }

  @Test
  void theVisitorCanStopEarly() throws Exception {
    Path file = write("h.jsonl", HEADER + "{\"itemKey\":\"1\"}\n{\"itemKey\":\"2\"}\n");
    List<Line> seen = new ArrayList<>();

    boolean finished =
        reader.forEachLine(
            file,
            line -> {
              seen.add(line);
              return false;
            });

    assertThat(finished).isFalse();
    assertThat(seen).hasSize(1);
  }

  @Test
  void anItemLineCanBeFoundByItsKey() throws Exception {
    Path file =
        write("i.jsonl", HEADER + "{\"itemKey\":\"1\",\"x\":1}\n{\"itemKey\":\"2\",\"x\":2}\n");

    assertThat(reader.findItem(file, "2").path("x").asInt()).isEqualTo(2);
    assertThat(reader.findItem(file, "9")).isNull();
  }
}
