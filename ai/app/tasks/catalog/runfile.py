"""실행 결과 파일(JSONL). 수집기가 쓰고 백엔드는 읽기만 한다.

첫 줄은 header, 이후 한 줄이 상품 하나(itemKey, collected, evidence, raw)다.
백엔드는 파일의 상대 이름만 받아 근거를 찾아가므로 이름은 디렉터리를 벗어날 수 없다.
이미지는 저장하지 않고 URL과 해시만 남긴다.
"""

import json
import os
import re
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from app.tasks.catalog.contract import RunHeader, RunItem

FILE_SUFFIX = ".jsonl"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$")
FILE_PATTERN = re.compile(r"^\d{8}-\d{6}-[A-Za-z0-9][A-Za-z0-9._-]{0,59}\.jsonl$")
CHECKPOINT_PATTERN = re.compile(r"^\d{8}-\d{6}-[A-Za-z0-9][A-Za-z0-9._-]{0,59}\.checkpoint\.json$")
ITEM_KEY_WIDTH = 6


class RunFileError(Exception):
    """파일 이름이 안전하지 않거나 내용이 계약과 다르다."""


def run_file_name(started_at: datetime, name: str) -> str:
    """<시작시각>-<실행 이름>.jsonl. 백엔드에는 이 상대 이름만 넘긴다."""
    if not NAME_PATTERN.fullmatch(name):
        raise RunFileError("실행 이름은 영문·숫자·._-만 쓰고 60자까지다")
    return f"{started_at.strftime('%Y%m%d-%H%M%S')}-{name}{FILE_SUFFIX}"


def resolve_in(directory: Path, file_name: str) -> Path:
    """상대 이름을 directory 안의 경로로 바꾼다. 절대 경로·하위 경로·.. 은 거절한다."""
    if not FILE_PATTERN.fullmatch(file_name):
        raise RunFileError("실행 결과 파일 이름 형식이 아니다")
    path = (directory / file_name).resolve()
    if path.parent != directory.resolve():
        raise RunFileError("실행 결과 폴더 밖의 파일이다")
    return path


def format_item_key(sequence: int) -> str:
    return f"{sequence:0{ITEM_KEY_WIDTH}d}"


def _line(model: RunHeader | RunItem) -> str:
    payload = model.model_dump(mode="json", by_alias=True)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _drop_incomplete_tail(path: Path) -> None:
    """쓰다가 끊긴 마지막 줄을 잘라낸다. 줄은 항상 줄바꿈으로 끝나게 쓰므로 그 앞까지만 믿는다."""
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    keep = data.rfind(b"\n") + 1
    with path.open("r+b") as handle:
        handle.truncate(keep)


class RunFileWriter:
    """한 번의 실행이 쓰는 파일. 줄을 하나씩 이어 쓰고, 끊긴 실행은 이어서 쓸 수 있다."""

    def __init__(self, path: Path, header: RunHeader, next_sequence: int) -> None:
        self.path = path
        self.header = header
        self._sequence = next_sequence
        self._handle = path.open("a", encoding="utf-8", newline="\n")

    @classmethod
    def create(cls, directory: Path, header: RunHeader, name: str) -> Self:
        """새 파일을 만들고 header를 쓴다. 같은 이름이 이미 있으면 덮어쓰지 않고 실패한다."""
        directory.mkdir(parents=True, exist_ok=True)
        path = resolve_in(directory, run_file_name(header.started_at, name))
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(_line(header) + "\n")
        return cls(path, header, 1)

    @classmethod
    def resume(cls, path: Path) -> Self:
        """끊긴 파일을 이어 쓴다. 마지막 줄이 끊겨 있으면 잘라내고, 줄 번호는 이어서 센다."""
        _drop_incomplete_tail(path)
        header, items = read_run_file(path)
        last = 0
        for item in items:
            last = int(item.item_key)
        return cls(path, header, last + 1)

    def next_item_key(self) -> str:
        return format_item_key(self._sequence)

    def append(self, item: RunItem) -> None:
        """상품 한 줄을 쓴다. itemKey는 next_item_key로 받은 순번이어야 한다."""
        if item.item_key != self.next_item_key():
            raise RunFileError(f"다음 itemKey는 {self.next_item_key()}여야 한다")
        self._handle.write(_line(item) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._sequence += 1

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def read_run_file(path: Path) -> tuple[RunHeader, Iterator[RunItem]]:
    """header와 상품 줄들을 읽는다. 줄이 계약과 다르면 RunFileError다."""
    handle = path.open(encoding="utf-8")
    first = handle.readline()
    if not first:
        handle.close()
        raise RunFileError("빈 파일이다")
    try:
        header = RunHeader.model_validate_json(first)
    except ValueError as error:
        handle.close()
        raise RunFileError(f"header가 계약과 다르다: {error}") from error

    def items() -> Iterator[RunItem]:
        with handle:
            for number, line in enumerate(handle, start=2):
                if not line.strip():
                    continue
                try:
                    yield RunItem.model_validate_json(line)
                except ValueError as error:
                    raise RunFileError(f"{number}번째 줄이 계약과 다르다: {error}") from error

    return header, items()


def cleanup_old_files(directory: Path, *, keep_days: int, now: float | None = None) -> list[Path]:
    """수정한 지 keep_days일이 지난 실행 결과 파일을 지우고 지운 파일을 돌려준다.

    이름 형식이 맞는 파일(체크포인트 포함)만 대상이라 폴더에 있는 다른 파일은 건드리지 않는다.
    """
    if not directory.is_dir():
        return []
    limit = (time.time() if now is None else now) - keep_days * 86400
    removed: list[Path] = []
    for path in sorted(directory.iterdir()):
        matches = FILE_PATTERN.fullmatch(path.name) or CHECKPOINT_PATTERN.fullmatch(path.name)
        if path.is_file() and matches and path.stat().st_mtime < limit:
            path.unlink()
            removed.append(path)
    return removed
