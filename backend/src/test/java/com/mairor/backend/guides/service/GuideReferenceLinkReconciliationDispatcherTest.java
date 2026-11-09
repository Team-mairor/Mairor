package com.mairor.backend.guides.service;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.when;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.guides.repository.GuideRepository;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;

@ExtendWith(MockitoExtension.class)
class GuideReferenceLinkReconciliationDispatcherTest {

  @Mock private TaskExecutor executor;
  @Mock private GuideRepository guides;
  @Mock private GuideStepProductLinkReconciler reconciler;

  @InjectMocks private GuideReferenceLinkReconciliationDispatcher dispatcher;

  @Test
  void rejectedAutomaticScheduleDoesNotEscapeAfterGuideCommit() {
    UUID guideId = UUID.randomUUID();
    doThrow(new TaskRejectedException("queue is full")).when(executor).execute(any(Runnable.class));

    assertThatCode(() -> dispatcher.scheduleAfterCommit(guideId)).doesNotThrowAnyException();
  }

  @Test
  void failedBackgroundReconciliationDoesNotEscapeTheCallbackThread() {
    UUID guideId = UUID.randomUUID();
    doAnswer(
            invocation -> {
              ((Runnable) invocation.getArgument(0)).run();
              return null;
            })
        .when(executor)
        .execute(any(Runnable.class));
    doThrow(new IllegalStateException("catalog unavailable")).when(reconciler).reconcile(guideId);

    assertThatCode(() -> dispatcher.scheduleAfterCommit(guideId)).doesNotThrowAnyException();
  }

  @Test
  void rejectedManualScheduleReturnsServiceUnavailable() {
    UUID guideId = UUID.randomUUID();
    when(guides.existsById(guideId)).thenReturn(true);
    doThrow(new TaskRejectedException("queue is full")).when(executor).execute(any(Runnable.class));

    assertThatThrownBy(() -> dispatcher.requestManualReconciliation(guideId))
        .isInstanceOf(BusinessException.class)
        .extracting(exception -> ((BusinessException) exception).code())
        .isEqualTo("SERVICE_UNAVAILABLE");
  }
}
