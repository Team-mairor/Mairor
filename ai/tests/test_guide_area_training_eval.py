import numpy as np

from app.tasks.area.common.face_map import MAP_SIZE, face_cells
from app.tasks.area.parts.eyeliner_area import eyeliner_range
from app.tasks.area.parts.eyeshadow_area import eyeshadow_range
from tools.guide_area_training import eval_fallback, eval_real, eval_synthetic, labels


def row(
    name: str, class_name: str, clean: bool, both: int, either: int, truth: int, guessed: int
) -> dict:
    return {
        "name": name,
        "className": class_name,
        "clean": clean,
        "method": "rule",
        "found": guessed > 0,
        "both": both,
        "either": either,
        "truth": truth,
        "guessed": guessed,
        "valid": 100,
    }


def test_summarize_adds_cells_over_cases_before_dividing_like_the_training_score():
    """IoU는 정답지마다 낸 값의 평균이 아니라 칸 수를 모두 더한 뒤 나눈다(train.py와 같은 정의)."""
    rows = [
        row("a", "lip", False, both=10, either=10, truth=10, guessed=10),
        row("b", "lip", False, both=0, either=30, truth=30, guessed=0),
    ]

    lip = eval_synthetic.summarize(rows, ["a", "b"])["rule"]["classes"]["lip"]

    assert lip["iou"] == 10 / 40
    assert lip["foundShare"] == 0.5
    assert lip["halfGap"] == 1.0


def test_summarize_counts_cells_painted_on_clean_cases_separately_from_class_scores():
    rows = [
        row("a", "blush", False, both=5, either=8, truth=6, guessed=7),
        row("c", "blush", True, both=0, either=4, truth=0, guessed=4),
    ]

    out = eval_synthetic.summarize(rows, ["a", "c"])["rule"]

    assert out["classes"]["blush"]["cases"] == 1
    assert out["cleanFalsePositive"] == 4 / 100
    assert out["cleanFoundShare"] == 1.0


def test_guessed_unknown_keeps_hidden_face_cells_but_not_faint_edges_or_outside_face():
    """정답지 모름 칸에는 흐린 가장자리·얼굴 밖도 들어 있어, 가려진 칸만 부위 함수에 넘겨야 한다."""
    face = face_cells()
    row_, col = np.argwhere(face)[len(np.argwhere(face)) // 2]
    label = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
    label[~face] = labels.IGNORE
    label[row_, col] = labels.IGNORE
    label[row_, col + 1] = labels.IGNORE
    strength = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
    strength[row_ + 5, col] = 255
    strength[row_, col + 1] = 60

    unknown = eval_synthetic.guessed_unknown(label, strength)

    assert unknown[row_, col]
    assert not unknown[row_, col + 1]
    assert not (unknown & ~face).any()


def test_words_of_splits_area_text_on_commas_middle_dots_and_and():
    assert eval_fallback.words_of("윗눈두덩, 애교살·눈꼬리 및 눈 앞머리") == [
        "윗눈두덩",
        "애교살",
        "눈꼬리",
        "눈 앞머리",
    ]
    assert eval_fallback.words_of("") == []


def test_zone_of_picks_the_fence_holding_more_of_the_area():
    """섀도·아이라인 하위 단계의 자리는 사람이 적지 않고 서비스 울타리와 겹친 칸 수로 정한다."""
    under = eyeshadow_range("leftEye", "under") & ~eyeshadow_range("leftEye", "upper")
    upper_line = eyeliner_range("rightEye", "upper") & ~eyeliner_range("rightEye", "under")

    assert eval_fallback.zone_of("eyeshadow", under) == "under"
    assert eval_fallback.zone_of("eyeliner", upper_line) == "upper"
    assert eval_fallback.zone_of("lip", under) is None


def test_word_map_keeps_cells_painted_in_more_than_half_of_the_matching_steps():
    first = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    second = first.copy()
    first[10:20, 10:20] = True
    second[15:25, 15:25] = True
    rows = [
        {"makeup": "lip", "zone": None, "words": ["입술"], "mask": first},
        {"makeup": "lip", "zone": None, "words": ["입술"], "mask": second},
        {"makeup": "lip", "zone": None, "words": ["입술 산"], "mask": first},
    ]

    out = eval_fallback.word_map(rows, "lip", None, "입술")

    assert out[17, 17]
    assert not out[12, 12]
    assert eval_fallback.word_map(rows, "lip", None, "볼") is None


def test_scores_marks_an_empty_guess_as_not_made():
    truth = np.zeros((4, 4), dtype=bool)
    truth[:2] = True
    guess = np.zeros((4, 4), dtype=bool)
    guess[1:3] = True

    assert eval_fallback.scores(None, truth)["made"] is False
    assert eval_fallback.scores(guess, truth) == {
        "iou": 4 / 12,
        "cover": 0.5,
        "overflow": 0.5,
        "made": True,
    }


def test_real_summary_counts_color_not_found_and_big_errors_per_part():
    rows = [
        {
            "sample": "v",
            "stepId": "s1",
            "makeup": "lip",
            "status": "extracted",
            "reasons": [],
            "colorNotFound": False,
            "bigError": True,
        },
        {
            "sample": "v",
            "stepId": "s2",
            "makeup": "lip",
            "status": "template",
            "reasons": ["lipColorNotFound"],
            "colorNotFound": True,
            "bigError": False,
        },
        {
            "sample": "v",
            "stepId": "s3",
            "makeup": "brow",
            "status": "template",
            "reasons": ["noUsableFrame"],
            "colorNotFound": False,
            "bigError": False,
        },
    ]

    out = eval_real.summarize(rows)["all"]

    assert out["extracted"] == 1
    assert out["colorNotFound"] == 1
    assert out["bigErrors"] == 1
    assert out["parts"]["brow"]["reasons"] == {"noUsableFrame": 1}


def test_big_error_allows_eye_overlap_up_to_the_reference_video_and_template():
    """아이라인은 원래 눈 테두리에 붙어, 기준 영상에서 찾은 값까지는 큰 오류로 치지 않는다."""
    reference = [
        {"makeup": "eyeliner", "status": "extracted", "eyeRatio": 0.2, "outsideRatio": 0.0},
        {"makeup": "eyeliner", "status": "template", "eyeRatio": 0.9, "outsideRatio": 0.9},
    ]
    rows = [
        {
            "makeup": "eyeliner",
            "status": "extracted",
            "eyeRatio": 0.15,
            "outsideRatio": 0.0,
            "templateEyeRatio": 0.0,
            "templateOutsideRatio": 0.0,
        },
        {
            "makeup": "eyeliner",
            "status": "extracted",
            "eyeRatio": 0.3,
            "outsideRatio": 0.0,
            "templateEyeRatio": 0.0,
            "templateOutsideRatio": 0.0,
        },
        {
            "makeup": "lip",
            "status": "extracted",
            "eyeRatio": 0.0,
            "outsideRatio": 0.01,
            "templateEyeRatio": 0.0,
            "templateOutsideRatio": 0.0,
        },
    ]

    limits = eval_real.reference_limits(reference)
    eval_real.mark_big_errors(rows, limits)

    assert limits == {"eyeliner": (0.2, 0.0)}
    assert [row["bigError"] for row in rows] == [False, True, True]
