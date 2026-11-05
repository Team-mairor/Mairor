package com.mairor.backend.products.imports;

/**
 * 두 색의 차이 ΔE2000(CIEDE2000). 재수집 때 이름이 없는 칸을 위치로 맞출 때, 같은 칸의 색이 크게 바뀌지 않았는지 확인하는 데 쓴다.
 *
 * <p>입력은 {@code #RRGGBB}(sRGB)이고 D65 기준 Lab 으로 바꿔 계산한다. 공식은 Sharma 등의 구현 노트를 따른다.
 */
public final class ColorDifference {

  private ColorDifference() {}

  /**
   * @param hexA {@code #RRGGBB} (대소문자 무관)
   * @param hexB {@code #RRGGBB} (대소문자 무관)
   * @throws IllegalArgumentException 형식이 틀리면
   */
  public static double deltaE2000(String hexA, String hexB) {
    double[] a = toLab(hexA);
    double[] b = toLab(hexB);
    return deltaE2000(a[0], a[1], a[2], b[0], b[1], b[2]);
  }

  /** CIEDE2000. 가중치 kL=kC=kH=1. */
  static double deltaE2000(double l1, double a1, double b1, double l2, double a2, double b2) {
    double c1 = Math.hypot(a1, b1);
    double c2 = Math.hypot(a2, b2);
    double cBar = (c1 + c2) / 2.0;
    double cBar7 = Math.pow(cBar, 7);
    double g = 0.5 * (1.0 - Math.sqrt(cBar7 / (cBar7 + Math.pow(25.0, 7))));
    double a1p = (1.0 + g) * a1;
    double a2p = (1.0 + g) * a2;
    double c1p = Math.hypot(a1p, b1);
    double c2p = Math.hypot(a2p, b2);
    double h1p = hueDegrees(b1, a1p);
    double h2p = hueDegrees(b2, a2p);

    double dLp = l2 - l1;
    double dCp = c2p - c1p;
    double dhp;
    if (c1p * c2p == 0.0) {
      dhp = 0.0;
    } else {
      double diff = h2p - h1p;
      if (diff > 180.0) {
        diff -= 360.0;
      } else if (diff < -180.0) {
        diff += 360.0;
      }
      dhp = diff;
    }
    double dHp = 2.0 * Math.sqrt(c1p * c2p) * Math.sin(Math.toRadians(dhp / 2.0));

    double lBarP = (l1 + l2) / 2.0;
    double cBarP = (c1p + c2p) / 2.0;
    double hBarP;
    if (c1p * c2p == 0.0) {
      hBarP = h1p + h2p;
    } else if (Math.abs(h1p - h2p) <= 180.0) {
      hBarP = (h1p + h2p) / 2.0;
    } else if (h1p + h2p < 360.0) {
      hBarP = (h1p + h2p + 360.0) / 2.0;
    } else {
      hBarP = (h1p + h2p - 360.0) / 2.0;
    }

    double t =
        1.0
            - 0.17 * Math.cos(Math.toRadians(hBarP - 30.0))
            + 0.24 * Math.cos(Math.toRadians(2.0 * hBarP))
            + 0.32 * Math.cos(Math.toRadians(3.0 * hBarP + 6.0))
            - 0.20 * Math.cos(Math.toRadians(4.0 * hBarP - 63.0));
    double dTheta = 30.0 * Math.exp(-Math.pow((hBarP - 275.0) / 25.0, 2));
    double cBarP7 = Math.pow(cBarP, 7);
    double rc = 2.0 * Math.sqrt(cBarP7 / (cBarP7 + Math.pow(25.0, 7)));
    double sl =
        1.0 + (0.015 * Math.pow(lBarP - 50.0, 2)) / Math.sqrt(20.0 + Math.pow(lBarP - 50.0, 2));
    double sc = 1.0 + 0.045 * cBarP;
    double sh = 1.0 + 0.015 * cBarP * t;
    double rt = -Math.sin(Math.toRadians(2.0 * dTheta)) * rc;

    double lTerm = dLp / sl;
    double cTerm = dCp / sc;
    double hTerm = dHp / sh;
    return Math.sqrt(lTerm * lTerm + cTerm * cTerm + hTerm * hTerm + rt * cTerm * hTerm);
  }

  private static double hueDegrees(double b, double ap) {
    if (b == 0.0 && ap == 0.0) {
      return 0.0;
    }
    double h = Math.toDegrees(Math.atan2(b, ap));
    return h < 0.0 ? h + 360.0 : h;
  }

  /** sRGB(#RRGGBB) → CIE L*a*b* (D65). */
  static double[] toLab(String hex) {
    if (hex == null || !hex.matches("^#[0-9A-Fa-f]{6}$")) {
      throw new IllegalArgumentException("#RRGGBB 형식이어야 한다");
    }
    double r = linear(Integer.parseInt(hex.substring(1, 3), 16) / 255.0);
    double g = linear(Integer.parseInt(hex.substring(3, 5), 16) / 255.0);
    double b = linear(Integer.parseInt(hex.substring(5, 7), 16) / 255.0);
    double x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b;
    double y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b;
    double z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b;
    double fx = labF(x / 0.95047);
    double fy = labF(y / 1.0);
    double fz = labF(z / 1.08883);
    return new double[] {116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)};
  }

  private static double linear(double c) {
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }

  private static double labF(double t) {
    double epsilon = 216.0 / 24389.0;
    double kappa = 24389.0 / 27.0;
    return t > epsilon ? Math.cbrt(t) : (kappa * t + 16.0) / 116.0;
  }
}
