package com.mairor.backend.matching.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import com.mairor.backend.matching.dto.CreateGuideMatchRequest;
import com.mairor.backend.matching.entity.GuideMatch;
import com.mairor.backend.matching.repository.GuideMatchRepository;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.products.repository.ProductShadeRepository;
import java.util.List;
import java.util.Optional;
import java.util.OptionalLong;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.ObjectMapper;

@ExtendWith(MockitoExtension.class)
class GuideMatchGenerationServiceTest {

  @Mock private GuideRepository guides;
  @Mock private GuideStepProductLinkRepository productLinks;
  @Mock private PouchItemRepository pouchItems;
  @Mock private PouchVersionRepository pouchVersions;
  @Mock private ProductShadeRepository shades;
  @Mock private GuideMatchRepository matches;

  private final ObjectMapper objectMapper = new ObjectMapper();
  private GuideMatchGenerationService service;

  @BeforeEach
  void setUp() {
    service =
        new GuideMatchGenerationService(
            guides,
            productLinks,
            pouchItems,
            pouchVersions,
            shades,
            matches,
            new ReferenceColorResolver(),
            new PouchCandidateAssembler(),
            new RecommendationCandidateSelector(),
            objectMapper);
  }

  @Test
  void createsNoneForGuideStepWhenPouchIsEmptyAndSkipsExcludedStep() {
    UUID userId = UUID.randomUUID();
    UUID guideId = UUID.randomUUID();
    Guide guide =
        approvedGuide(
            guideId,
            2,
            3,
            """
        {"steps":[
          {"stepId":"s1","makeup":"blush"},
          {"stepId":"s2","makeup":"other"}
        ]}
        """);
    when(pouchVersions.findByUserId(userId)).thenReturn(OptionalLong.of(4));
    when(guides.findById(guideId)).thenReturn(Optional.of(guide));
    when(pouchItems.findByUserIdOrderByCreatedAtDescIdDesc(userId)).thenReturn(List.of());
    when(productLinks.findByGuideIdOrderByStepIdAsc(guideId)).thenReturn(List.of());
    when(matches.saveAndFlush(any(GuideMatch.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));

    var response = service.create(userId, new CreateGuideMatchRequest(guideId));

    assertThat(response.pouchVersion()).isEqualTo(4);
    assertThat(response.steps()).hasSize(1);
    assertThat(response.steps().get(0).path("result").asString()).isEqualTo("NONE");
    assertThat(response.steps().get(0).path("noneReason").asString()).isEqualTo("NO_ITEMS");
    assertThat(response.steps().get(0).path("comparisonAvailable").asBoolean()).isFalse();
    assertThat(response.steps().get(0).path("alternatives").isArray()).isTrue();
    assertThat(response.steps().get(0).path("alternatives").size()).isZero();

    var saved = org.mockito.ArgumentCaptor.forClass(GuideMatch.class);
    verify(matches).saveAndFlush(saved.capture());
    var snapshot = objectMapper.readTree(saved.getValue().getMatchSnapshot());
    assertThat(snapshot.path("steps").size()).isEqualTo(1);
    assertThat(snapshot.path("referenceColors").path("s1").isNull()).isTrue();
  }

  @Test
  void getUsesOwnerScopedMatchAndKeepsSnapshotWhenPouchVersionChanged() {
    UUID userId = UUID.randomUUID();
    UUID otherUserId = UUID.randomUUID();
    UUID guideId = UUID.randomUUID();
    UUID matchId = UUID.randomUUID();
    String snapshot =
        """
        {"steps":[{"stepId":"s1","result":"SAME"}],"referenceColors":{}}
        """;
    GuideMatch match = new GuideMatch(matchId, userId, guideId, 2, 4, 3, 1, snapshot);
    Guide guide = org.mockito.Mockito.mock(Guide.class);
    when(matches.findByIdAndUserId(matchId, userId)).thenReturn(Optional.of(match));
    when(guides.findById(guideId)).thenReturn(Optional.of(guide));
    when(pouchVersions.findByUserId(userId)).thenReturn(OptionalLong.of(5));

    var response = service.get(userId, matchId);

    assertThat(response.stale()).isTrue();
    assertThat(response.steps().get(0).path("result").asString()).isEqualTo("SAME");
    verify(matches).findByIdAndUserId(matchId, userId);
    assertThatThrownBy(() -> service.get(otherUserId, matchId))
        .isInstanceOf(BusinessException.class);
  }

  private static Guide approvedGuide(
      UUID guideId, int version, int referenceVersion, String input) {
    Guide guide = org.mockito.Mockito.mock(Guide.class);
    when(guide.getId()).thenReturn(guideId);
    when(guide.getVersion()).thenReturn(version);
    when(guide.getReferenceVersion()).thenReturn(referenceVersion);
    when(guide.getGuideInput()).thenReturn(input);
    when(guide.getReviewStatus()).thenReturn(ReviewStatus.APPROVED);
    return guide;
  }
}
