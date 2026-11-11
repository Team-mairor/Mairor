package com.mairor.backend.executions.service;

import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.camera.service.FaceRegistrationExecutionService;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.executions.dto.CreateExecutionRequest;
import com.mairor.backend.executions.dto.ExecutionResponse;
import com.mairor.backend.executions.entity.ExecutionStatus;
import com.mairor.backend.executions.entity.ExecutionStep;
import com.mairor.backend.executions.entity.GuideExecution;
import com.mairor.backend.executions.repository.ExecutionStepRepository;
import com.mairor.backend.executions.repository.GuideExecutionRepository;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import com.mairor.backend.guides.service.GuideQueryService;
import com.mairor.backend.matching.repository.GuideMatchRepository;
import com.mairor.backend.matching.service.PouchCompatibilityPolicy;
import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.repository.ProductShadeRepository;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

/**
 * 가이드 공유 잠금 → 회원 → 실행/등록 → 사진 순서다. 가이드/색 변경 writer와 역순 잠금을 만들지 않는다. 회원 잠금 후 파우치/버전, 가이드 잠금 후 내용/연결을
 * 읽어 생성·불변 선택·얼굴 연결·이전 실행 종료를 함께 커밋한다.
 */
@Service
public class ExecutionCreationService {
  private final GuideRepository guides;
  private final GuideMatchRepository matches;
  private final PouchVersionRepository versions;
  private final PouchItemRepository pouch;
  private final ProductShadeRepository shades;
  private final GuideStepProductLinkRepository links;
  private final FaceRegistrationRepository registrations;
  private final StoredPhotoRepository photos;
  private final GuideExecutionRepository executions;
  private final ExecutionStepRepository steps;
  private final GuideQueryService guideQuery;
  private final FaceRegistrationExecutionService faceExecutions;
  private final ExecutionSelectionAssembler selections;
  private final ExecutionReplacementService replacement;
  private final ExecutionQueryService query;
  private final ObjectMapper mapper;

  public ExecutionCreationService(
      GuideRepository guides,
      GuideMatchRepository matches,
      PouchVersionRepository versions,
      PouchItemRepository pouch,
      ProductShadeRepository shades,
      GuideStepProductLinkRepository links,
      FaceRegistrationRepository registrations,
      StoredPhotoRepository photos,
      GuideExecutionRepository executions,
      ExecutionStepRepository steps,
      GuideQueryService guideQuery,
      FaceRegistrationExecutionService faceExecutions,
      ExecutionSelectionAssembler selections,
      ExecutionReplacementService replacement,
      ExecutionQueryService query,
      ObjectMapper mapper) {
    this.guides = guides;
    this.matches = matches;
    this.versions = versions;
    this.pouch = pouch;
    this.shades = shades;
    this.links = links;
    this.registrations = registrations;
    this.photos = photos;
    this.executions = executions;
    this.steps = steps;
    this.guideQuery = guideQuery;
    this.faceExecutions = faceExecutions;
    this.selections = selections;
    this.replacement = replacement;
    this.query = query;
    this.mapper = mapper;
  }

  @Transactional(isolation = Isolation.READ_COMMITTED)
  public ExecutionResponse create(UUID userId, String sessionId, CreateExecutionRequest request) {
    var match =
        matches
            .findByIdAndUserId(request.matchId(), userId)
            .orElseThrow(ExecutionCreationService::notFound);
    if (!match.getGuideId().equals(request.guideId())) {
      throw notFound();
    }
    var guide =
        guides.findByIdForShare(request.guideId()).orElseThrow(ExecutionCreationService::notFound);
    long pouchVersion =
        versions.lockByUserId(userId).orElseThrow(ExecutionCreationService::notFound);
    FaceRegistration face =
        registrations
            .findOwnedForUpdate(request.faceRegistrationId(), userId)
            .filter(
                value ->
                    value.getSessionId().equals(sessionId)
                        && value.getDiscardedAt() == null
                        && value.getVideoId().equals(guide.getVideo().getId()))
            .orElseThrow(ExecutionCreationService::notFound);
    Map<UUID, PouchItem> items =
        pouch.findByUserIdOrderByCreatedAtDescIdDesc(userId).stream()
            .collect(Collectors.toMap(PouchItem::getId, Function.identity()));
    selections.verifyOwnership(request.selections(), items);
    if (face.getStatus() != FaceRegistrationStatus.REGISTERED) {
      throw new BusinessException(
          HttpStatus.CONFLICT, "FACE_REGISTRATION_ALREADY_USED", "다른 실행에 이미 사용한 얼굴 등록입니다.");
    }
    if (match.getPouchVersion() != pouchVersion
        || match.getGuideVersion() != guide.getVersion()
        || match.getReferenceVersion() != guide.getReferenceVersion()
        || match.getCompatibilityVersion() != PouchCompatibilityPolicy.VERSION
        || guide.getReviewStatus() != ReviewStatus.APPROVED) {
      throw ExecutionSelectionAssembler.stale();
    }
    // 상태를 바꾸기 전에 이미지 존재/용도도 검증한다. link에서 잠금 후 다시 검증한다.
    photos
        .findByIdAndUserId(face.getPhotoId(), userId)
        .filter(
            value ->
                value.getKind() == PhotoKind.FACE_REGISTRATION
                    && value.getState() == PhotoState.AVAILABLE)
        .orElseThrow(ExecutionCreationService::notFound);
    var guideSnapshot = guideQuery.get(guide.getId());
    var shadeIds =
        items.values().stream()
            .map(PouchItem::getShadeId)
            .filter(java.util.Objects::nonNull)
            .distinct()
            .toList();
    Map<UUID, ProductShade> byShade =
        shadeIds.isEmpty()
            ? Map.of()
            : shades.findByIdIn(shadeIds).stream()
                .collect(Collectors.toMap(ProductShade::getId, Function.identity()));
    var byStep =
        links.findByGuideIdOrderByStepIdAsc(guide.getId()).stream()
            .collect(Collectors.toMap(value -> value.getStepId(), Function.identity()));
    var prepared =
        selections.assemble(
            guideSnapshot,
            mapper.readTree(match.getMatchSnapshot()),
            request.selections(),
            items,
            byShade,
            byStep,
            request.acceptMissingProducts());
    var previous =
        executions.findByUserIdAndSessionIdAndStatusOrderById(
            userId, sessionId, ExecutionStatus.IN_PROGRESS);
    GuideExecution execution =
        executions.saveAndFlush(
            new GuideExecution(
                UUID.randomUUID(),
                userId,
                sessionId,
                guide.getId(),
                match.getId(),
                face.getId(),
                guide.getVersion(),
                pouchVersion,
                guide.getReferenceVersion(),
                PouchCompatibilityPolicy.VERSION,
                mapper.writeValueAsString(guideSnapshot)));
    int position = 0;
    for (var step : prepared) {
      steps.save(
          new ExecutionStep(
              execution,
              step.stepId(),
              position++,
              step.skipped(),
              mapper.writeValueAsString(step.snapshot())));
    }
    faceExecutions.link(
        userId,
        sessionId,
        face.getId(),
        guide.getVideo().getId(),
        guide.getId(),
        execution.getId());
    replacement.abandon(previous);
    executions.flush();
    return query.response(execution);
  }

  private static BusinessException notFound() {
    return new BusinessException(ErrorCode.NOT_FOUND);
  }
}
