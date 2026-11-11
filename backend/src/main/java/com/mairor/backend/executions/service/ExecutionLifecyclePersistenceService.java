package com.mairor.backend.executions.service;

import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.camera.service.FaceRegistrationExecutionService;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.executions.dto.ExecutionAbandonmentResponse;
import com.mairor.backend.executions.entity.ExecutionStatus;
import com.mairor.backend.executions.entity.GuideExecution;
import com.mairor.backend.executions.repository.ExecutionStepRepository;
import com.mairor.backend.executions.repository.GuideExecutionRepository;
import com.mairor.backend.photos.service.PhotoRecordService;
import com.mairor.backend.users.repository.UserRepository;
import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 실행·얼굴 등록·사진 접근을 한 DB 트랜잭션에서 종료 상태로 전환한다. */
@Service
public class ExecutionLifecyclePersistenceService {
  private final UserRepository users;
  private final GuideExecutionRepository executions;
  private final ExecutionStepRepository steps;
  private final FaceRegistrationExecutionService faces;
  private final FaceRegistrationRepository faceRegistrations;
  private final PhotoRecordService photos;
  private final Clock clock;

  public ExecutionLifecyclePersistenceService(
      UserRepository users,
      GuideExecutionRepository executions,
      ExecutionStepRepository steps,
      FaceRegistrationExecutionService faces,
      FaceRegistrationRepository faceRegistrations,
      PhotoRecordService photos,
      Clock clock) {
    this.users = users;
    this.executions = executions;
    this.steps = steps;
    this.faces = faces;
    this.faceRegistrations = faceRegistrations;
    this.photos = photos;
    this.clock = clock;
  }

  @Transactional
  public AbandonedExecution abandon(UUID userId, String sessionId, UUID executionId) {
    users.findByIdForUpdate(userId).orElseThrow(ExecutionLifecyclePersistenceService::notFound);
    GuideExecution execution =
        executions
            .findOwnedForUpdate(executionId, userId)
            .orElseThrow(ExecutionLifecyclePersistenceService::notFound);
    if (!execution.getSessionId().equals(sessionId)) throw notFound();
    if (execution.getStatus() == ExecutionStatus.COMPLETED) {
      throw new BusinessException(
          HttpStatus.CONFLICT, "GUIDE_EXECUTION_ALREADY_COMPLETED", "완료된 가이드 실행은 중도 종료할 수 없습니다.");
    }
    List<UUID> photoIds = new ArrayList<>();
    if (execution.getStatus() == ExecutionStatus.IN_PROGRESS) {
      for (var step : steps.findByExecutionIdOrderByPosition(executionId)) {
        if (step.getPhotoId() != null) photoIds.add(step.getPhotoId());
      }
      photoIds.add(
          faces.abandon(userId, sessionId, execution.getFaceRegistrationId(), execution.getId()));
      photoIds.stream().distinct().sorted().forEach(photos::requestCleanupInCurrentTransaction);
      execution.abandon(clock.instant());
    } else {
      steps.findByExecutionIdOrderByPosition(executionId).stream()
          .map(step -> step.getPhotoId())
          .filter(java.util.Objects::nonNull)
          .forEach(photoIds::add);
      faceRegistrations
          .findOwnedForUpdate(execution.getFaceRegistrationId(), userId)
          .map(registration -> registration.getPhotoId())
          .ifPresent(photoIds::add);
    }
    return new AbandonedExecution(
        new ExecutionAbandonmentResponse(executionId, ExecutionStatus.ABANDONED, false),
        photoIds.stream().distinct().sorted().toList());
  }

  @Transactional
  public List<SessionAbandonment> abandonSession(UUID userId, String sessionId) {
    if (users.findByIdForUpdate(userId).isEmpty()) return List.of();
    List<SessionAbandonment> results = new ArrayList<>();
    for (GuideExecution execution :
        executions.findByUserIdAndSessionIdAndStatusOrderById(
            userId, sessionId, ExecutionStatus.IN_PROGRESS)) {
      List<UUID> photoIds = new ArrayList<>();
      for (var step : steps.findByExecutionIdOrderByPosition(execution.getId())) {
        if (step.getPhotoId() != null) photoIds.add(step.getPhotoId());
      }
      photoIds.add(
          faces.abandon(userId, sessionId, execution.getFaceRegistrationId(), execution.getId()));
      photoIds.stream().distinct().sorted().forEach(photos::requestCleanupInCurrentTransaction);
      execution.abandon(clock.instant());
      results.add(new SessionAbandonment(execution.getId(), photoIds.stream().distinct().toList()));
    }
    return List.copyOf(results);
  }

  private static BusinessException notFound() {
    return new BusinessException(ErrorCode.NOT_FOUND);
  }

  public record AbandonedExecution(ExecutionAbandonmentResponse response, List<UUID> photoIds) {}

  public record SessionAbandonment(UUID executionId, List<UUID> photoIds) {}
}
