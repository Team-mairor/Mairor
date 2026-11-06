# 눈썹 인식 실험

`/debug/guide-compare`의 실시간 카메라·눈썹 모드에서 사용한다. 기본값은 꺼짐이다.

1. `npm run brow:assets`로 모델·WASM을 준비한다.
2. **실제 눈썹 인식 (실험)** 을 켜고 정면에서 **다시 인식**을 누른다.
3. 검출 경계와 결을 확인한다. 끄면 기본 가이드로 돌아간다.

추론은 Web Worker에서 단일 스레드로 실행하며 사진을 서버에 보내지 않는다.
검출 결과는 얼굴 메시에 붙이며 매 프레임 재검출하지 않는다. 조명·자세·눈썹 모양이 바뀌면 다시 인식한다.
추적 상실·입력 변경·실험 종료 때 결과를 지우고, 종료 시 Worker도 정리한다.

양쪽 눈썹의 확률(0.55 이상), 연결 성분·면적·길이·경계 연속성을 검사한다.
실패 시 안내하고 가이드를 비운다. 이 기준은 실험용이다.

## 모델 출처

모델: [yakhyo/face-parsing ResNet18 v0.0.1](https://github.com/yakhyo/face-parsing/releases/download/v0.0.1/resnet18.onnx), 53,205,364 bytes, SHA-256 `0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f`. 원본 19개 얼굴 부위 중 눈썹 라벨 2·3을 사용하고, RGB/ImageNet 정규화 및 512×512 입력을 따른다. [원본 추론 코드](https://github.com/yakhyo/face-parsing/blob/main/onnx_inference.py). 코드 라이선스는 MIT이고 학습 데이터 CelebAMask-HQ의 비상업 연구·교육 이용 조건은 기존 AI 모델과 같이 확인해야 한다. 현재는 개발 비교 화면에만 연결한다. 모델·WASM은 실험 옵션을 명시적으로 켠 빌드에만 배포한다.
