import type { MeshAnchor, Point } from "@/vision/face";

export const MESH_PATH = "/models";

export interface FaceMesh {
  triangles: [number, number, number][];
  /** 꼭짓점별 UV. 원점은 왼쪽 위 */
  uv: [number, number][];
}

let meshPromise: Promise<FaceMesh> | null = null;

async function loadJson(url: string) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`메시 파일을 불러오지 못했습니다: ${url} (${response.status})`);
  return response.json();
}

/** 레이어·가이드 파일이 따라야 하는 메시 번호표 버전 */
export const MESH_VERSION = "v1";

/** 기준점을 이 메시에서 쓸 수 없으면 이유를 돌려준다. 범위 밖 번호는 그리는 중에 오류를 낸다. */
export function anchorError(anchor: MeshAnchor, mesh: FaceMesh): string | null {
  const { triangle, bary } = anchor ?? {};
  if (!Number.isInteger(triangle) || triangle < 0 || triangle >= mesh.triangles.length) {
    return `삼각형 번호가 범위 밖입니다: ${triangle}`;
  }
  if (!Array.isArray(bary) || bary.length !== 3 || !bary.every(Number.isFinite)) {
    return `무게중심 형식이 맞지 않습니다: ${JSON.stringify(bary)}`;
  }
  const sum = bary[0] + bary[1] + bary[2];
  if (Math.abs(sum - 1) > 0.001) return `무게중심 합이 1이 아닙니다: ${sum}`;
  return null;
}

/** 삼각형 번호표와 UV를 한 번만 불러온다. */
export function loadFaceMesh(): Promise<FaceMesh> {
  meshPromise ??= Promise.all([
    loadJson(`${MESH_PATH}/triangles.${MESH_VERSION}.json`),
    loadJson(`${MESH_PATH}/uv.${MESH_VERSION}.json`),
  ])
    .then(([t, u]) => ({ triangles: t.triangles, uv: u.uv }))
    .catch((e) => {
      meshPromise = null;
      throw e;
    });
  return meshPromise;
}

/** 삼각형 꼭짓점에 무게중심 비율을 곱해 위치를 구한다. 삼각형 밖(음수 비율)도 그대로 계산된다. */
export function resolveAnchor(anchor: MeshAnchor, mesh: FaceMesh, landmarks: Point[]): Point {
  const [a, b, c] = mesh.triangles[anchor.triangle].map((i) => landmarks[i]);
  const [wa, wb, wc] = anchor.bary;
  return {
    x: a.x * wa + b.x * wb + c.x * wc,
    y: a.y * wa + b.y * wb + c.y * wc,
  };
}
