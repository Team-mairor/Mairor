"""찾은 단계를 guideInput 단계로 바꿀 때 makeup·eyeZone·사실 출처를 맞게 정하는지 확인한다."""

import unittest

from processor.tasks.guide_request.steps import normalize_steps


def step(**changes):
    value = {
        "productKind": "blush",
        "faceArea": "볼",
        "partLabel": "블러셔",
        "summary": "볼에 두드리기",
        "productName": "블러셔 A",
        "productType": "블러셔",
        "action": "두드리기",
        "evidence": "이 블러셔를 볼에 두드려 줄게요",
        "area": "볼",
        "areaSource": "explicit",
        "isCosmeticApplication": True,
        "absStart": 40,
        "absEnd": 60,
    }
    return value | changes


class GuideStepTests(unittest.TestCase):
    def test_lipstick_on_cheeks_follows_product_kind(self):
        lipstick = step(productName="립 A", productType="립스틱", productKind="lip")
        result = normalize_steps([lipstick])[0]
        self.assertEqual(result["makeup"], "lip")
        self.assertEqual(result["product"]["name"], "립 A")
        self.assertEqual(result["facts"]["area"], {"value": "볼", "source": "voice", "at": 40})

    def test_unknown_area_does_not_route_to_lips(self):
        result = normalize_steps(
            [step(productKind="lip", area=None, areaSource="unknown", faceArea=None)]
        )[0]
        self.assertEqual(result["makeup"], "other")
        self.assertEqual(result["facts"]["area"]["value"], "부위 미확정")
        self.assertEqual(result["facts"]["area"]["source"], "estimated")

    def test_eye_zone_is_sent_only_for_eye_makeup_and_unknown_kind_becomes_other(self):
        eye = normalize_steps([step(productKind="eyeshadow", area="애교살", faceArea="애교살")])
        self.assertEqual(eye[0]["eyeZone"], "under")
        cheek = normalize_steps([step(eyeZone="upper")])
        self.assertNotIn("eyeZone", cheek[0])
        unknown = normalize_steps([step(productKind=None)])
        self.assertEqual(unknown[0]["makeup"], "other")

    def test_eye_corners_follow_the_other_eye_area(self):
        def zone(kind, *areas):
            events = [{"faceArea": a} for a in areas]
            return normalize_steps([step(productKind=kind, faceArea=areas[0], events=events)])[0]

        self.assertEqual(zone("eyeshadow", "애교살", "눈 앞머리")["eyeZone"], "under")
        self.assertEqual(zone("eyeliner", "눈꼬리", "윗라인")["eyeZone"], "upper")
        self.assertEqual(zone("eyeliner", "아랫점막", "눈꼬리")["eyeZone"], "under")
        self.assertNotIn("eyeZone", zone("eyeshadow", "눈꼬리"))

    def test_only_concealer_follows_where_it_is_applied(self):
        under_eye = normalize_steps([step(productKind="concealer", faceArea="눈 밑")])[0]
        self.assertEqual((under_eye["makeup"], under_eye.get("eyeZone")), ("foundation", None))
        brow_gap = normalize_steps([step(productKind="concealer", faceArea="미간")])[0]
        self.assertEqual(brow_gap["makeup"], "highlight")
        cushion = normalize_steps([step(productKind="base", faceArea="이마")])[0]
        self.assertEqual(cushion["makeup"], "foundation")

    def test_speech_is_passed_on_only_when_there_is_some(self):
        said = [{"at": 41.0, "text": "볼에 톡톡 두드려 줄게요"}]
        self.assertEqual(normalize_steps([step(speech=said)])[0]["speech"], said)
        self.assertNotIn("speech", normalize_steps([step(speech=[])])[0])

    def test_context_is_not_reported_as_direct_voice_fact(self):
        area = normalize_steps([step(areaSource="context")])[0]["facts"]["area"]
        self.assertEqual(area["source"], "estimated")
        self.assertIsNone(area["at"])


if __name__ == "__main__":
    unittest.main()
