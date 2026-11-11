package com.mairor.backend.products.imports;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.storage.ObjectNotFoundException;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.products.imports.CatalogImportProperties.Source;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.UUID;
import java.util.function.Predicate;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 수집기가 쓴 실행 결과 파일(JSONL)을 읽는다. 첫 줄은 header({@code runId}, {@code startedAt}, {@code seed}, {@code
 * collectorVersion}), 이후 한 줄이 상품 하나({@code itemKey}, {@code collected}, {@code evidence[]}, {@code
 * raw})다. 서버는 읽기만 한다.
 *
 * <p>파일 이름은 {@code catalog.import.result-dir} 안의 상대 이름만 받는다. 경로 구분자와 상위 경로({@code ..})는 거절하고, 확인한
 * 경로가 폴더 밖이면 열지 않는다.
 *
 * <p>{@code catalog.import.source=storage}면 객체 저장소의 {@code 접두사 + 이름}을 그 폴더(캐시)에 받아서 연다. 받은 지 {@code
 * storage-cache-ttl}이 지나지 않았으면 다시 받지 않는다. 받는 동안에는 임시 파일에 쓰고 다 받은 뒤 바꿔치기한다. 새로 받을 때마다 캐시 폴더에서 {@code
 * storage-cache-ttl}이 지난 파일을 지운다. 지난 파일은 어차피 다시 받으므로 남겨 둘 이유가 없다.
 *
 * <p>수집기가 쓰다가 끊기면 마지막 줄이 잘려 있을 수 있다. 마지막 줄을 읽지 못하면 쓰다 만 줄로 보고 건너뛴다. 중간 줄을 읽지 못하면 읽지 못한 줄({@link
 * Line#node}가 {@code null})로 알리고 계속 읽는다.
 */
@Component
public class CatalogRunFileReader {

  public static final String INVALID_FILE = "INVALID_RESULT_FILE";
  public static final String FILE_NOT_FOUND = "RESULT_FILE_NOT_FOUND";

  private static final Pattern NAME = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._-]{0,199}\\.jsonl$");

  private final Path directory;
  private final ObjectMapper mapper;
  private final ObjectStorage storage;
  private final boolean fromStorage;
  private final String prefix;
  private final Duration cacheTtl;

  public CatalogRunFileReader(
      CatalogImportProperties properties, ObjectMapper mapper, ObjectStorage storage) {
    this.directory = properties.resultDir().toAbsolutePath().normalize();
    this.mapper = mapper;
    this.storage = storage;
    this.fromStorage = properties.source() == Source.STORAGE;
    this.prefix = properties.storagePrefix();
    this.cacheTtl = properties.storageCacheTtl();
  }

  /**
   * 파일 첫 줄.
   *
   * @param startedAt header 의 시작 시각. 없거나 형식이 틀리면 {@code null}
   */
  public record Header(String runId, Instant startedAt, String seed, String collectorVersion) {}

  /**
   * 파일의 한 줄.
   *
   * @param number 파일 안의 줄 번호(1부터. header 가 1)
   * @param node 읽은 JSON 객체. 읽지 못한 줄이면 {@code null}
   */
  public record Line(int number, JsonNode node) {}

  /**
   * 상대 이름을 폴더 안의 실제 파일로 바꾼다.
   *
   * @throws BusinessException 400 {@code INVALID_RESULT_FILE}: 이름이 규칙에 맞지 않거나 폴더 밖이면. 404 {@code
   *     RESULT_FILE_NOT_FOUND}: 파일이 없으면(올리지 않았거나 이름이 틀렸다). 503 {@code SERVICE_UNAVAILABLE}: 저장소에서
   *     받지 못하면
   */
  public Path resolve(String name) {
    if (name == null || !NAME.matcher(name).matches()) {
      throw new BusinessException(
          HttpStatus.BAD_REQUEST,
          INVALID_FILE,
          "파일 이름은 영문·숫자·._- 로 이루어진 .jsonl 이어야 하며 경로를 포함할 수 없습니다.");
    }
    Path file = directory.resolve(name).normalize();
    if (!file.startsWith(directory)) {
      throw new BusinessException(HttpStatus.BAD_REQUEST, INVALID_FILE, "폴더 밖의 파일은 열 수 없습니다.");
    }
    if (fromStorage && !isFresh(file)) {
      fetch(name, file);
    }
    if (!Files.isRegularFile(file)) {
      throw notFound(name);
    }
    return file;
  }

  private boolean isFresh(Path file) {
    try {
      return Files.isRegularFile(file)
          && Files.getLastModifiedTime(file).toInstant().isAfter(Instant.now().minus(cacheTtl));
    } catch (IOException e) {
      return false;
    }
  }

  private void fetch(String name, Path file) {
    // 이름이 점으로 시작해 NAME 규칙에 맞지 않으므로 받는 중인 파일은 resolve 로 열 수 없다
    Path part = directory.resolve("." + name + "." + UUID.randomUUID() + ".part");
    try {
      Files.createDirectories(directory);
      storage.download(prefix + name, part);
      move(part, file);
      purgeExpired(file);
    } catch (ObjectNotFoundException e) {
      throw notFound(name);
    } catch (StorageException e) {
      throw new BusinessException(
          ErrorCode.SERVICE_UNAVAILABLE, "실행 결과 파일을 저장소에서 받지 못했습니다: " + name);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    } finally {
      try {
        Files.deleteIfExists(part);
      } catch (IOException ignored) {
        // 지우지 못한 임시 파일은 이름 규칙상 열리지 않는다
      }
    }
  }

  /** 캐시 폴더에서 기간이 지난 결과 파일과 남은 임시 파일을 지운다. 방금 받은 파일은 남긴다. 지우지 못한 파일은 다음에 다시 시도한다. */
  private void purgeExpired(Path keep) {
    Instant limit = Instant.now().minus(cacheTtl);
    try (Stream<Path> entries = Files.list(directory)) {
      entries
          .filter(path -> !path.equals(keep))
          .filter(
              path -> {
                String name = path.getFileName().toString();
                return NAME.matcher(name).matches() || name.endsWith(".part");
              })
          .filter(path -> isOlderThan(path, limit))
          .forEach(
              path -> {
                try {
                  Files.deleteIfExists(path);
                } catch (IOException ignored) {
                  // 읽는 중이라 못 지운 파일은 다음 정리 때 지운다
                }
              });
    } catch (IOException ignored) {
      // 캐시 정리는 적재를 막지 않는다
    }
  }

  private static boolean isOlderThan(Path path, Instant limit) {
    try {
      return Files.getLastModifiedTime(path).toInstant().isBefore(limit);
    } catch (IOException e) {
      return false;
    }
  }

  private static void move(Path from, Path to) throws IOException {
    try {
      Files.move(from, to, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
    } catch (AtomicMoveNotSupportedException e) {
      Files.move(from, to, StandardCopyOption.REPLACE_EXISTING);
    }
  }

  private static BusinessException notFound(String name) {
    return new BusinessException(
        HttpStatus.NOT_FOUND,
        FILE_NOT_FOUND,
        "실행 결과 파일을 찾을 수 없습니다(저장소에 올리지 않았거나 이름이 다릅니다): " + name);
  }

  /**
   * 첫 줄(header)을 읽는다.
   *
   * @throws BusinessException 400 {@code INVALID_RESULT_FILE}: 첫 줄이 없거나 JSON 객체가 아니거나 {@code
   *     runId}가 없으면
   */
  public Header header(Path file) {
    try (BufferedReader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
      String first = reader.readLine();
      JsonNode node = first == null ? null : parse(first);
      if (node == null || !node.isObject() || node.path("runId").asString("").isBlank()) {
        throw new BusinessException(
            HttpStatus.BAD_REQUEST, INVALID_FILE, "첫 줄에 runId 가 있는 header 가 있어야 합니다.");
      }
      return new Header(
          node.path("runId").asString(),
          instant(node.path("startedAt")),
          text(node.path("seed")),
          text(node.path("collectorVersion")));
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  /**
   * header 다음 줄부터 차례로 {@code visitor}에 준다. {@code visitor}가 {@code false}를 돌려주면 멈춘다. 빈 줄은 건너뛴다.
   *
   * @return 끝까지 읽었으면 {@code true}, {@code visitor}가 멈췄으면 {@code false}
   */
  public boolean forEachLine(Path file, Predicate<Line> visitor) {
    try (BufferedReader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
      reader.readLine();
      String pending = reader.readLine();
      int number = 2;
      while (pending != null) {
        String next = reader.readLine();
        if (!pending.isBlank()) {
          JsonNode node = parse(pending);
          boolean lastLine = next == null;
          if (node == null && lastLine) {
            return true;
          }
          if (!visitor.test(new Line(number, node != null && node.isObject() ? node : null))) {
            return false;
          }
        }
        pending = next;
        number++;
      }
      return true;
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  /** 건 하나(itemKey)의 줄을 찾는다. 없으면 {@code null}. */
  public JsonNode findItem(Path file, String itemKey) {
    JsonNode[] found = new JsonNode[1];
    forEachLine(
        file,
        line -> {
          if (line.node() != null && itemKey.equals(line.node().path("itemKey").asString(null))) {
            found[0] = line.node();
            return false;
          }
          return true;
        });
    return found[0];
  }

  private JsonNode parse(String json) {
    try {
      return mapper.readTree(json);
    } catch (JacksonException e) {
      return null;
    }
  }

  private static Instant instant(JsonNode node) {
    try {
      return node.isString() ? OffsetDateTime.parse(node.asString()).toInstant() : null;
    } catch (RuntimeException e) {
      return null;
    }
  }

  private static String text(JsonNode node) {
    return node.isString() && !node.asString().isBlank() ? node.asString() : null;
  }
}
