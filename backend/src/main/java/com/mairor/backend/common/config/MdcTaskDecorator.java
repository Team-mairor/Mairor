package com.mairor.backend.common.config;

import java.util.Map;
import java.util.concurrent.Callable;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

/**
 * 다른 스레드에서 도는 일에 지금 스레드의 로그 칸(MDC)을 넘긴다. MDC 는 스레드마다 따로라 실행기(executor)로 넘긴 일에는 작업 ID 같은 칸이 따라가지
 * 않는다. 일이 끝나면 그 스레드의 원래 칸으로 되돌린다.
 */
public final class MdcTaskDecorator implements TaskDecorator {

  @Override
  public Runnable decorate(Runnable runnable) {
    Map<String, String> context = MDC.getCopyOfContextMap();
    return () -> {
      Map<String, String> previous = MDC.getCopyOfContextMap();
      apply(context);
      try {
        runnable.run();
      } finally {
        apply(previous);
      }
    };
  }

  /** {@link #decorate(Runnable)}와 같지만 값을 돌려주는 일에 쓴다(실행기에 직접 넘기는 {@link Callable}). */
  public static <T> Callable<T> withCurrentContext(Callable<T> callable) {
    Map<String, String> context = MDC.getCopyOfContextMap();
    return () -> {
      Map<String, String> previous = MDC.getCopyOfContextMap();
      apply(context);
      try {
        return callable.call();
      } finally {
        apply(previous);
      }
    };
  }

  private static void apply(Map<String, String> context) {
    if (context == null) {
      MDC.clear();
    } else {
      MDC.setContextMap(context);
    }
  }
}
