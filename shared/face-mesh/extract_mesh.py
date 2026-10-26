"""face_landmarker.task에 들어 있는 캐노니컬 메시에서 삼각형 번호표와 UV를 뽑는다.

    python extract_mesh.py

모델 파일을 바꿨을 때만 다시 실행한다. 표준 라이브러리만 쓴다.
같은 meshVersion 파일이 이미 있는데 내용이 다르면 덮어쓰지 않고 멈춘다. 그때는 MESH_VERSION을 올린다.
"""

import json
import struct
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
TASK = HERE / "face_landmarker.task"
METADATA = "geometry_pipeline_metadata_landmarks.binarypb"
MESH_VERSION = "v1"


def read_varint(buf: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = buf[i]
        i += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            return result, i


def read_fields(buf: bytes):
    """protobuf 메시지를 (필드 번호, wire type, 값)으로 나눈다."""
    i = 0
    while i < len(buf):
        key, i = read_varint(buf, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = read_varint(buf, i)
        elif wire == 1:
            value, i = buf[i : i + 8], i + 8
        elif wire == 2:
            size, i = read_varint(buf, i)
            value, i = buf[i : i + size], i + size
        elif wire == 5:
            value, i = buf[i : i + 4], i + 4
        else:
            raise ValueError(f"지원하지 않는 wire type: {wire}")
        yield number, wire, value


def load_mesh() -> tuple[list[list[float]], list[list[int]]]:
    # GeometryPipelineMetadata.canonical_mesh(1) → Mesh3d
    # Mesh3d: vertex_type(1), primitive_type(2), vertex_buffer(3, float), index_buffer(4, uint32)
    data = zipfile.ZipFile(TASK).read(METADATA)
    mesh = next(value for number, _, value in read_fields(data) if number == 1)

    vertex_type = primitive_type = 0
    floats: list[float] = []
    indices: list[int] = []
    for number, wire, value in read_fields(mesh):
        if number == 1:
            vertex_type = value
        elif number == 2:
            primitive_type = value
        elif number == 3:
            floats += struct.unpack(f"<{len(value) // 4}f", value) if wire == 2 else struct.unpack("<f", value)
        elif number == 4:
            if wire == 2:
                j = 0
                while j < len(value):
                    index, j = read_varint(value, j)
                    indices.append(index)
            else:
                indices.append(value)

    # VERTEX_PT(0): x, y, z, u, v / TRIANGLE(0)
    if vertex_type != 0 or primitive_type != 0:
        raise ValueError(f"예상과 다른 메시 형식: vertex={vertex_type}, primitive={primitive_type}")
    if len(floats) % 5 or len(indices) % 3:
        raise ValueError(f"메시 길이가 맞지 않습니다: 실수 {len(floats)}개, 번호 {len(indices)}개")
    vertex_count = len(floats) // 5
    if any(not 0 <= index < vertex_count for index in indices):
        raise ValueError(f"꼭짓점 번호가 범위(0~{vertex_count - 1})를 벗어납니다")
    vertices = [floats[k : k + 5] for k in range(0, len(floats), 5)]
    triangles = [indices[k : k + 3] for k in range(0, len(indices), 3)]
    return vertices, triangles


def to_json(body: dict) -> str:
    # 배열 하나를 한 줄에 써서 diff를 보기 쉽게 한다.
    lines = []
    for key, value in body.items():
        if isinstance(value, list):
            rows = ",\n".join(f"    {json.dumps(row)}" for row in value)
            lines.append(f'  "{key}": [\n{rows}\n  ]')
        else:
            lines.append(f'  "{key}": {json.dumps(value, ensure_ascii=False)}')
    return "{\n" + ",\n".join(lines) + "\n}\n"


def main() -> None:
    vertices, triangles = load_mesh()
    outputs = {
        f"triangles.{MESH_VERSION}.json": to_json(
            {
                "meshVersion": MESH_VERSION,
                "vertexCount": len(vertices),
                "triangles": triangles,
            }
        ),
        f"uv.{MESH_VERSION}.json": to_json(
            {
                "meshVersion": MESH_VERSION,
                "origin": "top-left",
                "uv": [[round(v[3], 6), round(v[4], 6)] for v in vertices],
            }
        ),
    }
    # 같은 버전 번호로 다른 내용을 쓰면 기존 레시피의 MeshAnchor가 어긋난다. 모두 확인한 뒤에 쓴다.
    for name, text in outputs.items():
        path = HERE / name
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise SystemExit(f"{name} 내용이 달라졌습니다. MESH_VERSION을 올린 뒤 다시 실행하세요.")
    for name, text in outputs.items():
        path = HERE / name
        if not path.exists():
            path.write_text(text, encoding="utf-8", newline="\n")
    print(f"꼭짓점 {len(vertices)}개, 삼각형 {len(triangles)}개")


if __name__ == "__main__":
    main()
