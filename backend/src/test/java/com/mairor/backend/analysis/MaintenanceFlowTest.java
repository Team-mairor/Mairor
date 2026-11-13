package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.common.external.youtube.YouTubeClient;
import com.mairor.backend.common.external.youtube.YouTubeException;
import com.mairor.backend.common.external.youtube.YouTubeVideo;
import com.mairor.backend.maintenance.JobFileCleanup;
import com.mairor.backend.maintenance.JobFileStore;
import com.mairor.backend.maintenance.VideoMetaRefresher;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

/**
 * 하루 한 번 운영 정리(S15P31A306-407): 끝난 작업의 저장소 파일 정리와 영상 메타 갱신을 PostgreSQL · 로컬 저장소로 확인한다. 스케줄러(worker
 * 프로파일)는 띄우지 않고 두 작업을 직접 부른다.
 */
class MaintenanceFlowTest extends AnalysisIntegrationTest {

  @Autowired private JobFileCleanup cleanup;
  @Autowired private JobFileStore store;
  @Autowired private VideoMetaRefresher refresher;

  @MockitoBean private YouTubeClient youTube;

  // --- 저장소 파일 정리 ---

  @Test
  void filesOfJobsFinishedMoreThanAWeekAgoAreDeletedButTheSourceStays() {
    UUID oldVideo = video("mntOld00001", "1 day");
    UUID oldJob = job(oldVideo, "COMPLETED", "DONE", "8 days");
    putObject("videos/mntOld00001/source.mp4");
    putObject(jobKey("mntOld00001", oldJob, "frames/000001.jpg"));
    putObject(jobKey("mntOld00001", oldJob, "guide_job_request.json"));
    putObject("videos/mntOld00001/frames/000001.jpg");
    UUID recentVideo = video("mntNew00001", "1 day");
    UUID recentJob = job(recentVideo, "COMPLETED", "DONE", "3 days");
    putObject(jobKey("mntNew00001", recentJob, "frames/000001.jpg"));
    putObject("videos/mntNew00001/frames/000001.jpg");

    JobFileCleanup.Result result = cleanup.run();

    assertThat(result).isEqualTo(new JobFileCleanup.Result(1, 3, 1, 0));
    assertThat(STORAGE_ROOT.resolve("videos/mntOld00001/jobs/" + oldJob)).doesNotExist();
    assertThat(STORAGE_ROOT.resolve("videos/mntOld00001/frames")).doesNotExist();
    assertThat(STORAGE_ROOT.resolve("videos/mntOld00001/source.mp4")).exists();
    assertThat(STORAGE_ROOT.resolve(jobKey("mntNew00001", recentJob, "frames/000001.jpg")))
        .exists();
    assertThat(STORAGE_ROOT.resolve("videos/mntNew00001/frames/000001.jpg")).exists();
  }

  @Test
  void sharedFramesStayWhileTheVideoIsStillInUse() {
    UUID busy = video("mntBusy0001", "1 day");
    UUID busyOldJob = job(busy, "COMPLETED", "DONE", "8 days");
    job(busy, "PENDING", "QUEUED", null);
    putObject(jobKey("mntBusy0001", busyOldJob, "frames/000001.jpg"));
    putObject("videos/mntBusy0001/frames/000001.jpg");
    UUID rerun = video("mntRerun001", "1 day");
    UUID rerunOldJob = job(rerun, "COMPLETED", "DONE", "8 days");
    job(rerun, "FAILED", "LOADING_VIDEO", "2 days");
    putObject(jobKey("mntRerun001", rerunOldJob, "frames/000001.jpg"));
    putObject("videos/mntRerun001/frames/000001.jpg");

    JobFileCleanup.Result result = cleanup.run();

    assertThat(result).isEqualTo(new JobFileCleanup.Result(2, 2, 0, 0));
    assertThat(STORAGE_ROOT.resolve("videos/mntBusy0001/jobs/" + busyOldJob)).doesNotExist();
    assertThat(STORAGE_ROOT.resolve("videos/mntBusy0001/frames/000001.jpg")).exists();
    assertThat(STORAGE_ROOT.resolve("videos/mntRerun001/frames/000001.jpg")).exists();
  }

  @Test
  void aRetryableFailureForgetsTheNotebookResultBeforeItsFilesGo() {
    UUID video = video("mntFail0001", "1 day");
    UUID jobId = job(video, "FAILED", "BUILDING_GUIDE", "8 days");
    String requestKey = jobKey("mntFail0001", jobId, "guide_job_request.json");
    jdbc.update(
        "update analysis_jobs set retryable = true, failure_code = 'ANALYSIS_TIMEOUT',"
            + " processor_request_key = ? where id = ?",
        requestKey,
        jobId);
    putObject(requestKey);

    cleanup.run();

    Map<String, Object> row =
        jdbc.queryForMap(
            "select status, retryable, processor_request_key from analysis_jobs where id = ?",
            jobId);
    assertThat(row.get("status")).isEqualTo("FAILED");
    assertThat(row.get("retryable")).isEqualTo(true);
    assertThat(row.get("processor_request_key")).as("다시 시도하면 처음부터").isNull();
    assertThat(STORAGE_ROOT.resolve(requestKey)).doesNotExist();
  }

  @Test
  void aJobIsReleasedOnlyWhileItIsStillFinishedBeforeTheKeepLine() {
    UUID video = video("mntLock0001", "1 day");
    UUID old = job(video, "FAILED", "LOADING_VIDEO", "8 days");
    UUID recent = job(video, "COMPLETED", "DONE", "3 days");
    UUID retried = job(video, "FAILED", "LOADING_VIDEO", "9 days");
    jdbc.update(
        "update analysis_jobs set status = 'PENDING', progress_stage = 'QUEUED', finished_at = null"
            + " where id = ?",
        retried);
    Instant keepFrom = Instant.now().minus(Duration.ofDays(7));

    assertThat(store.releaseForCleanup(old, keepFrom)).isTrue();
    assertThat(store.releaseForCleanup(recent, keepFrom)).isFalse();
    assertThat(store.releaseForCleanup(retried, keepFrom)).as("목록을 읽은 뒤 다시 시도함").isFalse();
  }

  @Test
  void jobsOlderThanTheLookbackAreNotListedAgain() {
    UUID video = video("mntAncient1", "1 day");
    UUID jobId = job(video, "COMPLETED", "DONE", "40 days");
    putObject(jobKey("mntAncient1", jobId, "frames/000001.jpg"));

    JobFileCleanup.Result result = cleanup.run();

    assertThat(result).isEqualTo(new JobFileCleanup.Result(0, 0, 0, 0));
  }

  // --- 영상 메타 갱신 ---

  @Test
  void metaOlderThan25DaysIsFetchedAgain() {
    UUID stale = video("mntMeta0001", "26 days");
    UUID fresh = video("mntMeta0002", "1 day");
    when(youTube.videos(List.of("mntMeta0001")))
        .thenReturn(
            List.of(youTubeVideo("mntMeta0001", "바뀐 제목", "0:00 시작\n1:30 베이스\n4:10 아이섀도", 900)));

    VideoMetaRefresher.Result result = refresher.run();

    assertThat(result).isEqualTo(new VideoMetaRefresher.Result(1, 0, 0, 0, false));
    Map<String, Object> row =
        jdbc.queryForMap(
            "select title, channel_title, duration_seconds, chapters::text as chapters,"
                + " meta_refreshed_at from videos where id = ?",
            stale);
    assertThat(row.get("title")).isEqualTo("바뀐 제목");
    assertThat(row.get("channel_title")).isEqualTo("새 채널");
    assertThat(row.get("duration_seconds")).isEqualTo(900);
    assertThat((String) row.get("chapters")).contains("베이스").contains("\"startSeconds\": 250");
    assertThat(refreshedAt(stale)).isAfter(Instant.now().minus(Duration.ofMinutes(1)));
    assertThat(refreshedAt(fresh)).isBefore(Instant.now().minus(Duration.ofHours(12)));
  }

  @Test
  void aVideoGoneFromYouTubeTakesItsPublicGuideDown() {
    UUID gone = video("mntGone0001", "26 days");
    UUID guide = approvedGuide(gone);
    when(youTube.videos(List.of("mntGone0001"))).thenReturn(List.of());

    VideoMetaRefresher.Result result = refresher.run();

    assertThat(result).isEqualTo(new VideoMetaRefresher.Result(0, 1, 1, 0, false));
    assertThat(
            jdbc.queryForObject(
                "select review_status from guides where id = ?", String.class, guide))
        .isEqualTo("REJECTED");
    assertThat(jdbc.queryForObject("select title from videos where id = ?", String.class, gone))
        .as("메타는 마지막 값을 둔다")
        .isEqualTo("제목");
    assertThat(refreshedAt(gone))
        .as("내일 다시 묻지 않는다")
        .isAfter(Instant.now().minus(Duration.ofMinutes(1)));
  }

  @Test
  void videosAreAskedFiftyAtATime() {
    for (int i = 0; i < 51; i++) {
      video("mntMany%04d".formatted(i), "26 days");
    }
    when(youTube.videos(anyList())).thenReturn(List.of());

    VideoMetaRefresher.Result result = refresher.run();

    @SuppressWarnings("unchecked")
    ArgumentCaptor<List<String>> ids = ArgumentCaptor.forClass(List.class);
    verify(youTube, times(2)).videos(ids.capture());
    assertThat(ids.getAllValues()).extracting(List::size).containsExactly(50, 1);
    assertThat(result.missing()).isEqualTo(51);
  }

  @Test
  void aYouTubeFailureStopsTheRunAndLeavesTheRestForTomorrow() {
    UUID stale = video("mntQuota001", "26 days");
    when(youTube.videos(any()))
        .thenThrow(new YouTubeException(YouTubeException.Kind.QUOTA_EXCEEDED, "할당량", null));

    VideoMetaRefresher.Result result = refresher.run();

    assertThat(result).isEqualTo(new VideoMetaRefresher.Result(0, 0, 0, 0, true));
    assertThat(refreshedAt(stale)).isBefore(Instant.now().minus(Duration.ofDays(25)));
  }

  @Test
  void nothingIsAskedWhenEveryVideoIsFresh() {
    video("mntFresh001", "1 day");

    refresher.run();

    verify(youTube, never()).videos(any());
  }

  private UUID video(String youtubeVideoId, String refreshedAgo) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into videos (id, youtube_video_id, title, channel_title, duration_seconds, chapters,"
            + " meta_refreshed_at, created_at, updated_at) values (?, ?, '제목', '채널', 600, '[]'::jsonb,"
            + " now() - cast(? as interval), now(), now())",
        id,
        youtubeVideoId,
        refreshedAgo);
    return id;
  }

  /** {@code finishedAgo}가 null 이면 끝나지 않은 작업이다. */
  private UUID job(UUID videoId, String status, String stage, String finishedAgo) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, attempt,"
            + " finished_at, created_at, updated_at)"
            + " values (?, ?, ?, ?, false, 1, now() - cast(? as interval), now(), now())",
        id,
        videoId,
        status,
        stage,
        finishedAgo);
    return id;
  }

  private UUID approvedGuide(UUID videoId) {
    UUID jobId = job(videoId, "COMPLETED", "DONE", "20 days");
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input,"
            + " created_at, updated_at) values (?, ?, ?, 1, 'APPROVED', '{}'::jsonb, now(), now())",
        id,
        videoId,
        jobId);
    return id;
  }

  private Instant refreshedAt(UUID videoId) {
    return jdbc.queryForObject(
            "select meta_refreshed_at from videos where id = ?", Timestamp.class, videoId)
        .toInstant();
  }

  private static String jobKey(String youtubeVideoId, UUID jobId, String file) {
    return "videos/" + youtubeVideoId + "/jobs/" + jobId + "/" + file;
  }

  private static YouTubeVideo youTubeVideo(
      String id, String title, String description, int durationSeconds) {
    return new YouTubeVideo(
        id,
        title,
        "새 채널",
        description,
        durationSeconds,
        "https://i.ytimg.com/vi/" + id + "/hqdefault.jpg",
        1000L,
        Instant.parse("2026-10-01T00:00:00Z"),
        "public",
        YouTubeVideo.CREATIVE_COMMON,
        false,
        "none");
  }
}
