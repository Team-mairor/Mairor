package com.mairor.backend.videos.support;

import com.mairor.backend.videos.dto.VideoChapter;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 설명란에서 챕터를 읽는다. YouTube 가 챕터로 인정하는 규칙을 따른다: 줄 맨 앞의 시각, 첫 챕터가 {@code 0:00}, 3개 이상, 시각이 커지는 순서. 규칙에
 * 안 맞으면 챕터가 없는 것으로 본다(빈 목록).
 */
public final class ChapterParser {

  private static final Pattern LINE =
      Pattern.compile(
          "^\\s*[\\[(]?((?:\\d{1,2}:)?\\d{1,2}:\\d{2})[\\])]?\\s*[-–—:|.)]*\\s*(.*?)\\s*$");
  private static final int MIN_CHAPTERS = 3;
  private static final int MAX_LABEL_LENGTH = 100;

  private ChapterParser() {}

  public static List<VideoChapter> parse(String description) {
    if (description == null || description.isBlank()) {
      return List.of();
    }
    List<VideoChapter> chapters = new ArrayList<>();
    for (String line : description.split("\\R")) {
      Matcher m = LINE.matcher(line);
      if (!m.matches()) {
        continue;
      }
      int seconds = seconds(m.group(1));
      String label = m.group(2);
      if (label.length() > MAX_LABEL_LENGTH) {
        label = label.substring(0, MAX_LABEL_LENGTH);
      }
      if (!chapters.isEmpty() && seconds <= chapters.getLast().startSeconds()) {
        return List.of();
      }
      chapters.add(new VideoChapter(seconds, label));
    }
    if (chapters.size() < MIN_CHAPTERS || chapters.getFirst().startSeconds() != 0) {
      return List.of();
    }
    return List.copyOf(chapters);
  }

  private static int seconds(String clock) {
    String[] parts = clock.split(":");
    int total = 0;
    for (String part : parts) {
      total = total * 60 + Integer.parseInt(part);
    }
    return total;
  }
}
