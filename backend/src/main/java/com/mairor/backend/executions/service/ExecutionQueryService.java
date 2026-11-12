package com.mairor.backend.executions.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.executions.dto.ExecutionResponse;
import com.mairor.backend.executions.entity.ExecutionStatus;
import com.mairor.backend.executions.entity.GuideExecution;
import com.mairor.backend.executions.repository.ExecutionStepRepository;
import com.mairor.backend.executions.repository.GuideExecutionRepository;
import com.mairor.backend.photos.dto.PhotoResponse;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 현재 가이드/파우치를 다시 조회하지 않고 실행 당시 스냅샷만 반환한다. */
@Service
public class ExecutionQueryService {
  private final GuideExecutionRepository executions;
  private final ExecutionStepRepository steps;
  private final StoredPhotoRepository photos;
  private final ObjectMapper mapper;

  public ExecutionQueryService(
      GuideExecutionRepository executions,
      ExecutionStepRepository steps,
      StoredPhotoRepository photos,
      ObjectMapper mapper) {
    this.executions = executions;
    this.steps = steps;
    this.photos = photos;
    this.mapper = mapper;
  }

  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public ExecutionResponse get(UUID userId, String sessionId, UUID executionId) {
    GuideExecution execution =
        executions
            .findByIdAndUserId(executionId, userId)
            .filter(value -> value.getStatus() != ExecutionStatus.ABANDONED)
            .filter(
                value ->
                    value.getStatus() == ExecutionStatus.COMPLETED
                        || value.getSessionId().equals(sessionId))
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    return response(execution);
  }

  /** 생성 트랜잭션에서도 같은 DTO 조립을 사용한다. 호출자가 소유권/상태를 검증한다. */
  ExecutionResponse response(GuideExecution execution) {
    var storedSteps = steps.findByExecutionIdOrderByPosition(execution.getId());
    var photoIds =
        storedSteps.stream()
            .map(value -> value.getPhotoId())
            .filter(java.util.Objects::nonNull)
            .toList();
    var byId =
        photoIds.isEmpty()
            ? Map.<UUID, StoredPhoto>of()
            : photos.findAllById(photoIds).stream()
                .collect(Collectors.toMap(value -> value.getId(), Function.identity()));
    List<JsonNode> result = new ArrayList<>();
    for (var step : storedSteps) {
      ObjectNode snapshot = (ObjectNode) mapper.readTree(step.getStepSnapshot());
      snapshot.putNull("photo");
      var photo = step.getPhotoId() == null ? null : byId.get(step.getPhotoId());
      if (photo != null
          && photo.getKind() == PhotoKind.STEP
          && photo.getState() == PhotoState.AVAILABLE
          && photo.getExpiresAt() == null
          && photo.getUserId().equals(execution.getUserId())
          && photo.getSessionId().equals(execution.getSessionId())
          && step.getStepId().equals(photo.getStepId())) {
        snapshot.set("photo", mapper.valueToTree(PhotoResponse.from(photo)));
      }
      result.add(snapshot);
    }
    return ExecutionResponse.from(execution, result);
  }
}
