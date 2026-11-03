package com.mairor.backend.analysis.extraction;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

/**
 * 단계 추출 지시문과 답 형식({@code resources/prompts/step-extraction.*}). 형준의 Gemini 시험 도구({@code
 * ai/tools/gemini_prompt.txt}·{@code gemini_video_test.py}의 {@code SCHEMA})를 옮기고, 바르는 자리가 바뀌면 단계를
 * 나누는 규칙과 경계 규칙을 더했다. 대표 장면 시각 칸은 쓰지 않아 뺐다.
 */
@Component
public class StepExtractionPrompt {

  /** 실행마다 비슷한 단계가 나오게 낮게 둔다(형준 시험과 같은 값). */
  public static final double TEMPERATURE = 0.2;

  private final String prompt;
  private final String responseSchema;

  public StepExtractionPrompt() {
    this.prompt = read("prompts/step-extraction.txt");
    this.responseSchema = read("prompts/step-extraction.schema.json");
  }

  public String prompt() {
    return prompt;
  }

  public String responseSchema() {
    return responseSchema;
  }

  private static String read(String path) {
    try {
      return new ClassPathResource(path).getContentAsString(StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new UncheckedIOException(path + " 을 읽지 못했습니다.", e);
    }
  }
}
