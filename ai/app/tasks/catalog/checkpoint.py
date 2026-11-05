"""실행의 진행 상태. 끊긴 실행을 이어서 하거나 실패한 것만 다시 하려고 남긴다.

키는 실행이 다루는 단위(예: 카테고리 주소, 상품 주소)이고 의미는 쓰는 쪽이 정한다.
저장은 임시 파일에 쓴 뒤 바꿔치기해서, 쓰는 도중에 끊겨도 이전 상태가 남는다.
"""

import json
import os
from pathlib import Path
from typing import Self

CHECKPOINT_SUFFIX = ".checkpoint.json"


class CheckpointError(Exception):
    """체크포인트 파일이 읽을 수 없는 모양이다."""


def checkpoint_path_for(run_file: Path) -> Path:
    """실행 결과 파일 옆에 두는 체크포인트 경로.

    20261105-103000-etude.jsonl → 20261105-103000-etude.checkpoint.json
    """
    return run_file.with_name(run_file.stem + CHECKPOINT_SUFFIX)


class Checkpoint:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self._done: set[str] = set()
        self._failed: dict[str, str] = {}

    @classmethod
    def load_or_create(cls, path: Path, run_id: str) -> Self:
        """파일이 있으면 읽고(run_id가 다르면 거절), 없으면 빈 상태로 시작한다."""
        checkpoint = cls(path, run_id)
        if not path.exists():
            return checkpoint
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stored = data["runId"]
            done = data["done"]
            failed = data["failed"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CheckpointError(f"체크포인트를 읽지 못했다: {path.name}") from error
        if stored != run_id:
            raise CheckpointError(f"다른 실행의 체크포인트다: {stored}")
        if not isinstance(done, list) or not isinstance(failed, dict):
            raise CheckpointError(f"체크포인트 모양이 다르다: {path.name}")
        checkpoint._done = {str(key) for key in done}
        checkpoint._failed = {str(key): str(reason) for key, reason in failed.items()}
        return checkpoint

    @property
    def done(self) -> frozenset[str]:
        return frozenset(self._done)

    @property
    def failed(self) -> dict[str, str]:
        return dict(self._failed)

    def is_done(self, key: str) -> bool:
        return key in self._done

    def mark_done(self, key: str) -> None:
        self._done.add(key)
        self._failed.pop(key, None)
        self.save()

    def mark_failed(self, key: str, reason: str) -> None:
        self._done.discard(key)
        self._failed[key] = reason
        self.save()

    def pending(self, keys: list[str], *, retry_failed: bool = False) -> list[str]:
        """아직 하지 않은 키. 실패한 키는 retry_failed일 때만 다시 한다."""
        return [
            key
            for key in keys
            if key not in self._done and (retry_failed or key not in self._failed)
        ]

    def failed_keys(self) -> list[str]:
        return sorted(self._failed)

    def save(self) -> None:
        payload = {
            "runId": self.run_id,
            "done": sorted(self._done),
            "failed": dict(sorted(self._failed.items())),
        }
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, self.path)
