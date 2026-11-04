"""합성 사진의 바탕이 될 가림 없는 얼굴을 진짜 사진 정답지에서 고른다(개발용).

바탕은 남긴 사진 중 자막이 없고 얼굴 안 가림이 OCCLUDED_MAX 이하인 사진이다.
<정답지 폴더>/<나눔>/bases.json에 [{"video", "frameIndex", "t"}, ...]로 적고 개수를 출력한다.

실행 (ai/ 폴더에서): uv run --no-sync python tools/occlusion_training/pick_bases.py [정답지 폴더]
정답지 폴더를 적지 않으면 <작업 폴더>/data/real이다.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from workspace import REAL_DIR

OCCLUDED_MAX = 0.0


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else REAL_DIR
    for split_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        bases = []
        for index_path in sorted(split_dir.glob("*/index.json")):
            video = index_path.parent.name
            for row in json.loads(index_path.read_text(encoding="utf-8")):
                clean = row.get("subtitle", 0) == 0 and row["occludedShare"] <= OCCLUDED_MAX
                if row["dropped"] is None and clean:
                    bases.append({"video": video, "frameIndex": row["frameIndex"], "t": row["t"]})
        (split_dir / "bases.json").write_text(
            json.dumps(bases, ensure_ascii=False, indent=0), encoding="utf-8"
        )
        print(split_dir.name, f"바탕 {len(bases)}장", dict(Counter(b["video"] for b in bases)))


if __name__ == "__main__":
    main()
