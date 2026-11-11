package com.mairor.backend.executions.service;

import com.mairor.backend.camera.service.FaceRegistrationExecutionService;
import com.mairor.backend.executions.entity.GuideExecution;
import com.mairor.backend.executions.repository.ExecutionStepRepository;
import com.mairor.backend.photos.service.PhotoRecordService;
import java.time.Clock;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 검증된 새 실행으로 교체할 때만 사용한다. 파일 I/O 없이 상태와 삭제 예약을 같은 트랜잭션에 저장한다. */
@Service
@Transactional(propagation = Propagation.MANDATORY)
public class ExecutionReplacementService {
  private final FaceRegistrationExecutionService faces;
  private final ExecutionStepRepository steps;
  private final PhotoRecordService photoRecords;
  private final Clock clock;

  public ExecutionReplacementService(
      FaceRegistrationExecutionService faces,
      ExecutionStepRepository steps,
      PhotoRecordService photoRecords,
      Clock clock) {
    this.faces = faces;
    this.steps = steps;
    this.photoRecords = photoRecords;
    this.clock = clock;
  }

  public void abandon(List<GuideExecution> previous) {
    for (GuideExecution execution : previous) {
      faces.abandon(
          execution.getUserId(),
          execution.getSessionId(),
          execution.getFaceRegistrationId(),
          execution.getId());
      for (var photoId :
          steps.findByExecutionIdOrderByPosition(execution.getId()).stream()
              .map(step -> step.getPhotoId())
              .filter(java.util.Objects::nonNull)
              .distinct()
              .sorted()
              .toList()) {
        photoRecords.requestCleanupInCurrentTransaction(photoId);
      }
      execution.abandon(clock.instant());
    }
  }
}
