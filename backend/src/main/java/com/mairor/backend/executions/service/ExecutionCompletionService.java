package com.mairor.backend.executions.service;

import com.mairor.backend.camera.service.FaceRegistrationExecutionService;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.executions.dto.ExecutionCompletionResponse;
import com.mairor.backend.executions.entity.ExecutionStatus;
import com.mairor.backend.executions.entity.ExecutionStep;
import com.mairor.backend.executions.entity.GuideExecution;
import com.mairor.backend.executions.repository.ExecutionStepRepository;
import com.mairor.backend.executions.repository.GuideExecutionRepository;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.history.entity.HistoryRecord;
import com.mairor.backend.history.repository.HistoryRecordRepository;
import com.mairor.backend.photos.dto.PhotoResponse;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.videos.entity.Video;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 실행 완료·불변 리포트 스냅샷·얼굴 보관을 하나의 DB 트랜잭션으로 묶는다. */
@Service
public class ExecutionCompletionService {
  private final UserRepository users;
  private final GuideExecutionRepository executions;
  private final ExecutionStepRepository steps;
  private final StoredPhotoRepository photos;
  private final GuideRepository guides;
  private final HistoryRecordRepository records;
  private final FaceRegistrationExecutionService faceRegistrations;
  private final ObjectMapper mapper;
  private final Clock clock;

  public ExecutionCompletionService(
      UserRepository users,
      GuideExecutionRepository executions,
      ExecutionStepRepository steps,
      StoredPhotoRepository photos,
      GuideRepository guides,
      HistoryRecordRepository records,
      FaceRegistrationExecutionService faceRegistrations,
      ObjectMapper mapper,
      Clock clock) {
    this.users = users;
    this.executions = executions;
    this.steps = steps;
    this.photos = photos;
    this.guides = guides;
    this.records = records;
    this.faceRegistrations = faceRegistrations;
    this.mapper = mapper;
    this.clock = clock;
  }

  @Transactional
  public CompletionResult complete(UUID userId, String sessionId, UUID executionId) {
    users.findByIdForUpdate(userId).orElseThrow(ExecutionCompletionService::notFound);
    GuideExecution execution =
        executions
            .findOwnedForUpdate(executionId, userId)
            .orElseThrow(ExecutionCompletionService::notFound);
    if (execution.getStatus() == ExecutionStatus.COMPLETED) {
      return new CompletionResult(
          new ExecutionCompletionResponse(
              execution.getId(),
              execution.getStatus(),
              execution.getRecordId(),
              execution.getCompletedAt()),
          false);
    }
    if (execution.getStatus() != ExecutionStatus.IN_PROGRESS) {
      throw new BusinessException(
          HttpStatus.CONFLICT, "GUIDE_EXECUTION_NOT_ACTIVE", "포기한 실행은 완료할 수 없습니다.");
    }
    if (!execution.getSessionId().equals(sessionId)) throw notFound();

    List<ExecutionStep> executionSteps = steps.findByExecutionIdOrderByPosition(executionId);
    Video video =
        guides
            .findById(execution.getGuideId())
            .map(guide -> guide.getVideo())
            .orElseThrow(ExecutionCompletionService::notFound);
    Instant completedAt = clock.instant().truncatedTo(ChronoUnit.MICROS);
    UUID recordId = UUID.randomUUID();
    ObjectNode report = buildReport(execution, executionSteps, video, recordId, completedAt);
    UUID completedPhotoId =
        report.path("completedPhoto").isObject()
            ? UUID.fromString(report.path("completedPhoto").path("photoId").asString())
            : null;
    int substitutes = (int) executionSteps.stream().filter(this::isSubstitute).count();
    records.saveAndFlush(
        new HistoryRecord(
            recordId,
            execution.getId(),
            userId,
            execution.getGuideId(),
            execution.getGuideVersion(),
            video.getId(),
            video.getYoutubeVideoId(),
            video.getTitle(),
            video.getChannelTitle(),
            video.getThumbnailUrl(),
            completedAt,
            completedPhotoId,
            executionSteps.size(),
            substitutes,
            mapper.writeValueAsString(report)));
    execution.complete(recordId, completedAt);
    faceRegistrations.retain(
        userId, sessionId, execution.getFaceRegistrationId(), execution.getId());
    return new CompletionResult(
        new ExecutionCompletionResponse(
            execution.getId(),
            execution.getStatus(),
            execution.getRecordId(),
            execution.getCompletedAt()),
        true);
  }

  private ObjectNode buildReport(
      GuideExecution execution,
      List<ExecutionStep> executionSteps,
      Video video,
      UUID recordId,
      java.time.Instant completedAt) {
    ObjectNode report = mapper.createObjectNode();
    report.put("recordId", recordId.toString());
    report.put("executionId", execution.getId().toString());
    report.put("videoId", video.getId().toString());
    report.put("videoTitle", video.getTitle());
    report.put("channelTitle", video.getChannelTitle());
    report.put("guideId", execution.getGuideId().toString());
    report.put("guideVersion", execution.getGuideVersion());
    report.put("completedAt", completedAt.toString());
    report.put("stepCount", executionSteps.size());
    int substitutes = (int) executionSteps.stream().filter(this::isSubstitute).count();
    report.put("substituteCount", substitutes);
    ArrayNode reportSteps = report.putArray("steps");
    for (ExecutionStep step : executionSteps) {
      ObjectNode snapshot = (ObjectNode) mapper.readTree(step.getStepSnapshot());
      if (snapshot.has("result")) {
        snapshot.set("matchingResult", snapshot.get("result"));
        snapshot.remove("result");
      }
      snapshot.remove("candidates");
      snapshot.remove("category");
      snapshot.remove("comparisonAvailable");
      snapshot.remove("samePouchItemId");
      snapshot.remove("noneReason");
      snapshot.remove("selectedPouchItemId");
      snapshot.putNull("photo");
      StoredPhoto photo = availableStepPhoto(execution, step);
      if (photo != null) snapshot.set("photo", mapper.valueToTree(PhotoResponse.from(photo)));
      reportSteps.add(snapshot);
    }
    ObjectNode completedPhoto = null;
    if (!executionSteps.isEmpty()) {
      ExecutionStep last = executionSteps.getLast();
      StoredPhoto photo = availableStepPhoto(execution, last);
      if (photo != null) completedPhoto = mapper.valueToTree(PhotoResponse.from(photo));
    }
    if (completedPhoto == null) report.putNull("completedPhoto");
    else report.set("completedPhoto", completedPhoto);
    return report;
  }

  private StoredPhoto availableStepPhoto(GuideExecution execution, ExecutionStep step) {
    if (step.isSkipped() || step.getPhotoId() == null) return null;
    return photos
        .findByIdAndUserId(step.getPhotoId(), execution.getUserId())
        .filter(
            photo ->
                photo.getKind() == PhotoKind.STEP
                    && photo.getState() == PhotoState.AVAILABLE
                    && photo.getExpiresAt() == null
                    && photo.getSessionId().equals(execution.getSessionId())
                    && photo.getStepId().equals(step.getStepId()))
        .orElse(null);
  }

  private boolean isSubstitute(ExecutionStep step) {
    return "SUBSTITUTE".equals(mapper.readTree(step.getStepSnapshot()).path("result").asString());
  }

  private static BusinessException notFound() {
    return new BusinessException(ErrorCode.NOT_FOUND);
  }

  public record CompletionResult(ExecutionCompletionResponse response, boolean newlyCompleted) {}
}
