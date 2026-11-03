package com.mairor.backend.analysis.extraction;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * AI 서버와 같은 공유 스키마({@code shared/guide-input/guide_input.v2.schema.json})로 가이드 입력을 검사한다. 테스트는
 * {@code backend/}에서 돌므로 레포의 파일을 바로 읽는다. 스키마가 바뀌어 BE 변환이 어긋나면 여기서 잡힌다.
 */
public final class GuideInputSchema {

  public static final Path FILE = Path.of("../shared/guide-input/guide_input.v2.schema.json");

  private static final JsonSchema SCHEMA = load();
  // 검사기는 Jackson 2 를 쓴다(앱은 Jackson 3)
  private static final ObjectMapper JSON = new ObjectMapper();

  private GuideInputSchema() {}

  /**
   * @return 어긋난 곳. 통과하면 빈 문자열
   */
  public static String violations(String guideInputJson) {
    try {
      Set<ValidationMessage> errors = SCHEMA.validate(JSON.readTree(guideInputJson));
      return errors.stream().map(ValidationMessage::getMessage).collect(Collectors.joining("\n"));
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  private static JsonSchema load() {
    try {
      return JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012)
          .getSchema(Files.readString(FILE));
    } catch (IOException e) {
      throw new UncheckedIOException(FILE.toAbsolutePath() + " 을 읽지 못했습니다.", e);
    }
  }
}
