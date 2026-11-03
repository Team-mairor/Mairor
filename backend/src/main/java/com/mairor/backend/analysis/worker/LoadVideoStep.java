package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.common.storage.ObjectNotFoundException;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import java.nio.file.Path;
import org.springframework.stereotype.Component;

/**
 * 영상 불러오기(LOADING_VIDEO): 운영자가 저장소에 올린 영상 파일을 작업 폴더로 내려받고 ffprobe 로 원본 정보(가로·세로·fps·길이)를 재서 {@code
 * videos}에 기록한다.
 */
@Component
class LoadVideoStep implements AnalysisStepHandler {

  private final ObjectStorage storage;
  private final Ffprobe ffprobe;
  private final AnalysisJobStore store;

  LoadVideoStep(ObjectStorage storage, Ffprobe ffprobe, AnalysisJobStore store) {
    this.storage = storage;
    this.ffprobe = ffprobe;
    this.store = store;
  }

  @Override
  public ProgressStage stage() {
    return ProgressStage.LOADING_VIDEO;
  }

  @Override
  public void run(AnalysisContext context) {
    String key = context.sourceObjectKey();
    if (key == null) {
      throw new AnalysisStepException(AnalysisFailureCode.SOURCE_NOT_FOUND, "영상 파일 키가 없습니다.");
    }
    Path file = context.workDir().resolve("source" + extension(key));
    try {
      storage.download(key, file);
    } catch (ObjectNotFoundException e) {
      throw new AnalysisStepException(
          AnalysisFailureCode.SOURCE_NOT_FOUND, "저장소에 영상 파일이 없습니다: " + key, e);
    } catch (StorageException e) {
      throw new AnalysisStepException(
          AnalysisFailureCode.STORAGE_UNAVAILABLE, "영상 파일을 내려받지 못했습니다: " + key, e);
    }

    VideoProbe probe;
    try {
      probe = ffprobe.probe(file);
    } catch (FfprobeException e) {
      throw new AnalysisStepException(AnalysisFailureCode.SOURCE_UNREADABLE, e.getMessage(), e);
    }
    store.recordSourceProbe(context.videoId(), probe);
    context.sourceLoaded(file, probe);
  }

  private static String extension(String key) {
    int slash = key.lastIndexOf('/');
    int dot = key.lastIndexOf('.');
    return dot > slash && dot < key.length() - 1 ? key.substring(dot) : "";
  }
}
