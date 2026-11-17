import importlib.util
from pathlib import Path

from app.tasks.area.landmarks.frame_checker import RATIO_WINDOW_MS
from app.tasks.area.reference_area import PART_WINDOWS

PROCESSOR_WINDOWS = (
    Path(__file__).resolve().parents[2] / "video-processor/processor/tasks/frames/windows.py"
)


def load_processor_windows():
    """노트북 처리기의 창 표 파일을 처리기 패키지 설치 없이 경로로 읽는다."""
    spec = importlib.util.spec_from_file_location("processor_windows", PROCESSOR_WINDOWS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_processor_window_table_matches_part_windows():
    """처리기가 뽑는 사진 구간이 AI 부위 창과 같아야 AI가 쓰는 사진이 빠지지 않는다.

    AI가 창을 정한 부위는 모두 처리기 창 표에도 있어야 한다. 처리기에 없는 부위는 사진이 오지 않아
    늘 기본 가이드로 나간다.
    """
    processor = load_processor_windows().AI_WINDOWS_MS

    assert processor == {makeup: PART_WINDOWS[makeup] for makeup in processor}
    assert set(PART_WINDOWS) == set(processor)


def test_processor_ratio_window_matches_frame_checker():
    """처리기가 창 앞뒤로 더 뽑는 길이가 AI 사진 판정이 견주는 길이와 같아야 한다."""
    assert load_processor_windows().RATIO_WINDOW_MS == RATIO_WINDOW_MS
