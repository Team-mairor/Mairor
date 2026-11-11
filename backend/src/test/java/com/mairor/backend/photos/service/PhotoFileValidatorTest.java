package com.mairor.backend.photos.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.photos.entity.StoredPhoto;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

class PhotoFileValidatorTest {
  private final PhotoTemporaryFiles temporaryFiles =
      new PhotoTemporaryFiles(
          Path.of(System.getProperty("java.io.tmpdir"), "mairor-photo-validator-tests"),
          Clock.systemUTC());
  private final PhotoFileValidator validator =
      new PhotoFileValidator(properties(25_000_000), temporaryFiles);

  static PhotoStorageProperties properties(long pixels) {
    return new PhotoStorageProperties(
        Duration.ofMinutes(10), Duration.ofMinutes(1), Duration.ofMinutes(1), 50, pixels, false);
  }

  static byte[] image(String type) throws Exception {
    BufferedImage image = new BufferedImage(3, 2, BufferedImage.TYPE_INT_RGB);
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    ImageIO.write(image, type, bytes);
    return bytes.toByteArray();
  }

  @Test
  void detectsPngFromBytesAndRemovesTheTemporaryFileOnClose() throws Exception {
    ValidatedPhoto result =
        validator.validate(
            new MockMultipartFile("image", "../../wrong.jpg", "image/jpeg", image("png")));
    assertThat(result.contentType()).isEqualTo("image/png");
    assertThat(result.width()).isEqualTo(3);
    assertThat(result.height()).isEqualTo(2);
    assertThat(result.path()).exists();
    result.close();
    assertThat(result.path()).doesNotExist();
  }

  @Test
  void decodesJpeg() throws Exception {
    try (ValidatedPhoto result =
        validator.validate(
            new MockMultipartFile("image", "face.jpg", "image/jpeg", image("jpeg")))) {
      assertThat(result.contentType()).isEqualTo("image/jpeg");
    }
  }

  @Test
  void rejectsGifAndNonImageBytesDespiteTheirDeclaredMime() throws Exception {
    assertCode(
        () ->
            validator.validate(
                new MockMultipartFile("image", "face.png", "image/png", image("gif"))),
        "UNSUPPORTED_MEDIA_TYPE");
    assertCode(
        () ->
            validator.validate(
                new MockMultipartFile("image", "face.png", "image/png", new byte[] {1, 2, 3})),
        "UNSUPPORTED_MEDIA_TYPE");
  }

  @Test
  void rejectsTruncatedPng() throws Exception {
    byte[] png = image("png");
    assertCode(
        () ->
            validator.validate(
                new MockMultipartFile(
                    "image", "face.png", "image/png", java.util.Arrays.copyOf(png, 35))),
        "UNSUPPORTED_MEDIA_TYPE");
  }

  @Test
  void rejectsMissingAndEmptyFiles() {
    assertCode(() -> validator.validate(null), "VALIDATION_FAILED");
    assertCode(
        () -> validator.validate(new MockMultipartFile("image", new byte[0])), "VALIDATION_FAILED");
  }

  @Test
  void checksActualStreamLengthEvenWhenTheReportedLengthIsFalse() {
    MockMultipartFile file =
        new MockMultipartFile("image", new byte[(int) StoredPhoto.MAX_BYTE_SIZE + 1]) {
          @Override
          public long getSize() {
            return 1;
          }
        };
    assertCode(() -> validator.validate(file), "PAYLOAD_TOO_LARGE");
  }

  @Test
  void rejectsOversizedReportedLengthBeforeReading() {
    assertCode(
        () ->
            validator.validate(
                new MockMultipartFile("image", new byte[(int) StoredPhoto.MAX_BYTE_SIZE + 1])),
        "PAYLOAD_TOO_LARGE");
  }

  @Test
  void limitsDecodedPixelsBeforeAllocatingTheImage() throws Exception {
    PhotoFileValidator small = new PhotoFileValidator(properties(5), temporaryFiles);
    assertCode(
        () -> small.validate(new MockMultipartFile("image", "face.png", "image/png", image("png"))),
        "PAYLOAD_TOO_LARGE");
  }

  private void assertCode(org.assertj.core.api.ThrowableAssert.ThrowingCallable call, String code) {
    assertThatThrownBy(call)
        .isInstanceOfSatisfying(
            BusinessException.class, exception -> assertThat(exception.code()).isEqualTo(code));
  }
}
