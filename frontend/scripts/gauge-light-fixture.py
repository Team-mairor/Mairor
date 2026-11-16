# 게이지 조명 보정(light.ts)이 AI baseline.light_change(OpenCV)와 같은 값을 내는지 볼 시험 데이터를 만든다.
# opencv-python-headless · numpy가 필요하다.
# python scripts/gauge-light-fixture.py ../shared/gauge/baseline.v1.json > src/features/gauge/light.fixture.json
import json, sys
import numpy as np, cv2
spec = json.load(open(sys.argv[1]))
G = spec["grid"]
mask = lambda rows: np.array([[c == "1" for c in r] for r in rows])
measured, skin = mask(spec["cells"]["measured"]), mask(spec["cells"]["skin"])
L = spec["light"]
i, j = np.mgrid[0:G, 0:G].astype(np.float64)
base = np.stack([60 + 5*np.sin(i/9) + 3*np.cos(j/11), 12 + 2*np.sin(j/7), 18 + 2*np.cos(i/13)], -1).astype(np.float32)
base[~measured] = np.nan
change = np.stack([-4 - 3*(j/(G-1)), 1.5*np.sin(i/20), 2*np.cos(j/17)], -1).astype(np.float32)
made = np.zeros((G, G), bool); made[70:81, 40:61] = True
current = base + change
current[made, 0] -= 10
current[made, 1] += 6
def grow(cells, m):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*m+1, 2*m+1))
    return cv2.dilate(cells.astype(np.uint8), k) > 0
grown = grow(made, L["marginCells"])
free = measured & skin & ~np.isnan(current).any(-1) & ~grown
w = free.astype(np.float32)
filled = np.where(free[..., None], current - base, 0).astype(np.float32)
total = np.stack([cv2.GaussianBlur(filled[..., c], (0, 0), L["sigmaCells"]) for c in range(3)], -1)
count = cv2.GaussianBlur(w, (0, 0), L["sigmaCells"])
light = total / np.maximum(count, L["minWeight"])[..., None]
cells = [int(k) for k in np.flatnonzero(measured)[::173]] + [int(r*G+c) for r in (70, 75, 80) for c in (40, 50, 60)] + [0, G-1, G*G-1]
print(json.dumps({"grownCount": int(grown.sum()), "freeCount": int(free.sum()),
  "light": {str(k): [round(float(v), 5) for v in light.reshape(-1, 3)[k]] for k in cells}}))
