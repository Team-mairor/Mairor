package com.mairor.backend.photos.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.photos.entity.StoredPhoto;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.Locale;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.MemoryCacheImageInputStream;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

/** 파일명·요청 MIME 대신 실제 파일 길이와 이미지 디코더로 검증한다. */
@Component
public class PhotoFileValidator {
  private final PhotoStorageProperties properties;
  private final PhotoTemporaryFiles temporaryFiles;

  public PhotoFileValidator(PhotoStorageProperties properties, PhotoTemporaryFiles temporaryFiles) {
    this.properties = properties;
    this.temporaryFiles = temporaryFiles;
  }

  public ValidatedPhoto validate(MultipartFile file) {
    if (file == null || file.isEmpty()) {
      throw new BusinessException(ErrorCode.VALIDATION_FAILED, "사진 파일이 필요합니다.");
    }
    if (file.getSize() > StoredPhoto.MAX_BYTE_SIZE) {
      throw tooLarge();
    }
    PhotoTemporaryFiles.Lease lease = temporaryFiles.create();
    Path path = lease.path();
    try {
      long size = copyBounded(file, path);
      if (size == 0) {
        throw new BusinessException(ErrorCode.VALIDATION_FAILED, "사진 파일이 비어 있습니다.");
      }
      return decode(lease, size);
    } catch (RuntimeException e) {
      try {
        lease.close();
      } catch (RuntimeException cleanup) {
        e.addSuppressed(cleanup);
      }
      throw e;
    }
  }

  private long copyBounded(MultipartFile file, Path path) {
    try (InputStream input = file.getInputStream();
        OutputStream output = Files.newOutputStream(path)) {
      byte[] buffer = new byte[8192];
      long total = 0;
      int read;
      while ((read = input.read(buffer)) != -1) {
        total += read;
        if (total > StoredPhoto.MAX_BYTE_SIZE) {
          throw tooLarge();
        }
        output.write(buffer, 0, read);
      }
      return total;
    } catch (IOException e) {
      throw new StorageException("사진 업로드 파일을 읽지 못했습니다", e);
    }
  }

  private ValidatedPhoto decode(PhotoTemporaryFiles.Lease lease, long size) {
    try (InputStream file = Files.newInputStream(lease.path());
        MemoryCacheImageInputStream input = new MemoryCacheImageInputStream(file)) {
      Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
      if (!readers.hasNext()) {
        throw unsupported();
      }
      ImageReader reader = readers.next();
      try {
        String format = reader.getFormatName().toLowerCase(Locale.ROOT);
        String contentType =
            switch (format) {
              case "jpeg", "jpg" -> "image/jpeg";
              case "png" -> "image/png";
              default -> throw unsupported();
            };
        reader.setInput(input, true, true);
        int width = reader.getWidth(0);
        int height = reader.getHeight(0);
        if (width < 1 || height < 1) {
          throw unsupported();
        }
        if ((long) width * height > properties.maxDecodedPixels()) {
          throw tooLarge();
        }
        BufferedImage decoded = reader.read(0);
        if (decoded == null) {
          throw unsupported();
        }
        decoded.flush();
        return new ValidatedPhoto(lease.path(), contentType, size, width, height, lease);
      } finally {
        reader.dispose();
      }
    } catch (IOException | IllegalArgumentException e) {
      throw unsupported();
    }
  }

  private static BusinessException tooLarge() {
    return new BusinessException(
        HttpStatus.PAYLOAD_TOO_LARGE, "PAYLOAD_TOO_LARGE", "사진 파일 크기 또는 해상도가 허용 범위를 초과했습니다.");
  }

  private static BusinessException unsupported() {
    return new BusinessException(
        HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_MEDIA_TYPE", "정상적인 JPEG 또는 PNG 사진이 필요합니다.");
  }
}
