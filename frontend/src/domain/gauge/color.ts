/** sRGB → XYZ 행렬과 D65 흰색. AI rgb_to_lab과 같은 값이다 */
const TO_XYZ = [
  [0.412453, 0.35758, 0.180423],
  [0.212671, 0.71516, 0.072169],
  [0.019334, 0.119193, 0.950227],
];
const WHITE = [0.950456, 1, 1.088754];
const EPS = (6 / 29) ** 3;
const POW_25_7 = 25 ** 7;

const linear = (v: number) => {
  const c = v / 255;
  return c > 0.04045 ? ((c + 0.055) / 1.055) ** 2.4 : c / 12.92;
};
const f = (t: number) => (t > EPS ? Math.cbrt(t) : t / (3 * (6 / 29) ** 2) + 4 / 29);

/** 0~255 RGB(소수 가능)를 Lab(D65)으로 바꾼다 */
export function rgbToLab(r: number, g: number, b: number): [number, number, number] {
  const rgb = [linear(r), linear(g), linear(b)];
  const [x, y, z] = TO_XYZ.map(
    (row, i) => (row[0] * rgb[0] + row[1] * rgb[1] + row[2] * rgb[2]) / WHITE[i],
  );
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
}

const rad = (deg: number) => (deg * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;
const mod360 = (v: number) => ((v % 360) + 360) % 360;

/** 두 Lab 색의 CIEDE2000 거리. AI delta_e_map과 같은 식이다 */
export function deltaE2000(
  l1: number,
  a1: number,
  b1: number,
  l2: number,
  a2: number,
  b2: number,
): number {
  const meanC = (Math.hypot(a1, b1) + Math.hypot(a2, b2)) / 2;
  const g = 0.5 * (1 - Math.sqrt(meanC ** 7 / (meanC ** 7 + POW_25_7)));
  const a1p = (1 + g) * a1;
  const a2p = (1 + g) * a2;
  const c1p = Math.hypot(a1p, b1);
  const c2p = Math.hypot(a2p, b2);
  const h1p = mod360(deg(Math.atan2(b1, a1p)));
  const h2p = mod360(deg(Math.atan2(b2, a2p)));
  const both = c1p * c2p !== 0;
  let dh = h2p - h1p;
  if (dh > 180) dh -= 360;
  else if (dh < -180) dh += 360;
  if (!both) dh = 0;
  const dL = l2 - l1;
  const dC = c2p - c1p;
  const dH = 2 * Math.sqrt(c1p * c2p) * Math.sin(rad(dh / 2));
  const meanL = (l1 + l2) / 2;
  const meanCp = (c1p + c2p) / 2;
  const totalH = h1p + h2p;
  let meanH =
    Math.abs(h1p - h2p) <= 180
      ? totalH / 2
      : totalH < 360
        ? (totalH + 360) / 2
        : (totalH - 360) / 2;
  if (!both) meanH = totalH;
  const t =
    1 -
    0.17 * Math.cos(rad(meanH - 30)) +
    0.24 * Math.cos(rad(2 * meanH)) +
    0.32 * Math.cos(rad(3 * meanH + 6)) -
    0.2 * Math.cos(rad(4 * meanH - 63));
  const dTheta = 30 * Math.exp(-(((meanH - 275) / 25) ** 2));
  const rC = 2 * Math.sqrt(meanCp ** 7 / (meanCp ** 7 + POW_25_7));
  const sL = 1 + (0.015 * (meanL - 50) ** 2) / Math.sqrt(20 + (meanL - 50) ** 2);
  const sC = 1 + 0.045 * meanCp;
  const sH = 1 + 0.015 * meanCp * t;
  const rT = -Math.sin(rad(2 * dTheta)) * rC;
  return Math.sqrt((dL / sL) ** 2 + (dC / sC) ** 2 + (dH / sH) ** 2 + rT * (dC / sC) * (dH / sH));
}
