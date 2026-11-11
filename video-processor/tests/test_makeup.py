"""부위 사전이 AI 서버 값과 맞고, makeup은 화장품 종류로, eyeZone은 부위 이름으로 정해지는지 확인한다."""

import unittest

from processor.schemas.makeup import EYE_ZONES, FACE_AREAS, MAKEUPS
from processor.tasks.guide_request.makeup import derive


class FaceAreaTests(unittest.TestCase):
    def test_every_area_maps_to_server_values(self):
        for name, (_group, zone, concealer) in FACE_AREAS.items():
            self.assertIn(zone, [*EYE_ZONES, None], name)
            self.assertIn(concealer, MAKEUPS, name)
        self.assertEqual(FACE_AREAS["윗점막"][1], "waterline")
        self.assertEqual(FACE_AREAS["아랫점막"][1], "under")

    def test_names_in_one_area_share_the_eye_zone(self):
        zones = {}
        for group, zone, _ in FACE_AREAS.values():
            self.assertEqual(zones.setdefault(group, zone), zone, group)

    def test_area_sets_zone_but_kind_comes_from_the_cosmetic(self):
        shadow = derive({"productKind": "eyeshadow", "faceArea": "위로 뺀 눈꼬리 라인"})
        self.assertEqual((shadow["makeup"], shadow.get("eyeZone")), ("eyeshadow", "upper"))
        blush = derive({"productKind": "blush", "faceArea": "눈 밑"})
        self.assertEqual((blush["makeup"], blush.get("eyeZone")), ("blush", None))

    def test_concealer_is_never_sent_as_an_analyzed_kind(self):
        for name, (_group, _zone, concealer) in FACE_AREAS.items():
            self.assertIn(concealer, ["foundation", "highlight"], name)

    def test_skincare_is_other(self):
        balm = derive({"productKind": "skincare", "faceArea": "입술", "isCosmeticApplication": True})
        self.assertEqual((balm["makeup"], balm.get("eyeZone")), ("other", None))


if __name__ == "__main__":
    unittest.main()
