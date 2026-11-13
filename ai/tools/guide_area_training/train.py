"""전후 얼굴 지도 두 장에서 바른 곳을 칠하는 모델을 학습한다(개발용, GPU).

입력은 단계 직전·직후 얼굴 지도(before.png·after.png)를 겹친 6겹이고, 출력은 칸마다 바른 자리
번호(labels.CLASSES)다. 정답의 모름 칸(labels.IGNORE)은 손실과 점수에서 뺀다.

출발 모델은 둘이다.
- bisenet: 얼굴 분할 모델 BiSeNet(ResNet18) 가중치에서 출발한다. 첫 층은 3겹에서 6겹으로 늘리고
  (전·후에 같은 가중치를 반씩), 세 출력 머리는 자리 번호 수에 맞춰 새로 만든다.
- small: 작은 모델(SmallNet)을 처음부터 학습한다.

묶음마다 실제 장면 정답지와 합성 정답지를 --real-share 비율로 섞는다. 한쪽이 없으면 있는 쪽만 쓴다.
에폭마다 검증 나눔(다른 채널 영상)을 재서 자리별 IoU 평균(meanIoU)이 가장 높은 가중치(best.pt)와
기록(log.json)을 남긴다. 시험 나눔은 여기서 읽지 않는다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/guide_area_training/train.py <결과 폴더 이름> \
    [--model bisenet|small] [--painted-weight 3] [--real-share 0.5] [--batch 4] [--lr 1e-4] \
    [--size 1024] [--epochs 15] [--patience 3] [--max-steps <걸음>] [--workers 2]
결과는 <작업 폴더>/runs/<결과 폴더 이름>/ 에 쓴다.
학습 패키지는 train 묶음이다(uv sync --group train).
bisenet은 <작업 폴더>/models/bisenet_resnet18.pt 가 있어야 한다.
받는 곳은 occlusion_training/README.md에 있다.
"""

import argparse
import json
import math
import random
import sys
import time
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torch import Tensor, nn
from torch.utils.data import DataLoader, Dataset

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parent / "occlusion_training"))

import labels
import workspace
from face_parsing.bisenet import BiSeNet

SEED = 428
NUM_CLASSES = len(labels.CLASSES)
PAINTED = tuple(range(1, NUM_CLASSES))
SOURCES = ("real", "synth")
RUNS_DIR = workspace.WORK_DIR / "runs"
BISENET_PT = workspace.WORK_DIR / "models" / "bisenet_resnet18.pt"
BACKBONE_LR_SHARE = 0.1
WEIGHT_DECAY = 1e-4
AUX_WEIGHT = 0.4
WARMUP_STEPS = 300
BRIGHTNESS = 0.15
SMALL_WIDTHS = (16, 32, 64, 128)
GROUPS = 8
VAL_BATCH = 4
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def sample_folders(split: str, source: str) -> list[Path]:
    """나눔·출처의 정답지 폴더 목록(list.jsonl 순서). 목록이 없으면 빈 목록이다."""
    folder = workspace.labels_dir(split, source)
    return [folder / row["name"] for row in labels.read_list(folder)]


def stack_maps(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """전후 얼굴 지도(RGB 0~255)를 6겹(겹이 앞, 0~255 그대로)으로 겹친다. 앞 3겹이 직전이다.

    소수로 바꾸는 계산은 GPU에서 한다(to_input). CPU에서 바꾸면 한 건이 네 배로 커지고 느려서다.
    """
    return np.concatenate([before, after], axis=2).transpose(2, 0, 1)


def to_input(maps: Tensor, gains: Tensor, device: str) -> Tensor:
    """6겹 지도 묶음(0~255)에 건마다 밝기 배수를 곱하고(0~255로 자름) 모델 입력으로 정규화한다."""
    mean = torch.tensor(np.tile(MEAN, 2), device=device).view(1, 6, 1, 1)
    std = torch.tensor(np.tile(STD, 2), device=device).view(1, 6, 1, 1)
    x = maps.to(device, non_blocking=True).float()
    x = (x * gains.to(device).float().view(-1, 1, 1, 1)).clamp(0, 255)
    return (x / 255 - mean) / std


def shrink(image: np.ndarray, size: int, label: bool = False) -> np.ndarray:
    """정사각형 지도를 size로 줄인다. 정답 그림은 번호가 섞이지 않게 가까운 칸 값을 쓴다."""
    if image.shape[0] == size:
        return image
    how = cv2.INTER_NEAREST if label else cv2.INTER_AREA
    return cv2.resize(image, (size, size), interpolation=how)


def load_sample(folder: Path, size: int) -> tuple[np.ndarray, np.ndarray]:
    """정답지 한 건을 (6겹 지도 0~255, 정답 그림)으로 읽는다. 크기는 size로 맞춘다."""
    before = shrink(labels.read_png(folder / "before.png", color=True), size)
    after = shrink(labels.read_png(folder / "after.png", color=True), size)
    label = shrink(labels.read_png(folder / "label.png"), size, label=True)
    return stack_maps(before, after), label


class Pairs(Dataset):
    """정답지 묶음. augment면 좌우 뒤집기와 밝기 변화를 준다.

    얼굴 지도는 좌우가 대칭이고 자리 번호에 왼쪽·오른쪽이 없어 뒤집어도 번호는 그대로다.
    밝기는 전후에 같은 배수를 곱한다. 한쪽만 바꾸면 바르지 않은 칸의 색이 달라져서다.
    preload면 처음에 모든 건을 읽어 메모리에 둔다(threads개로 나눠 읽음). PNG를 에폭마다 다시
    풀지 않아 CPU가 덜 막힌다. 학습 1,617건이면 약 11GB다.
    """

    def __init__(
        self,
        items: Sequence[tuple[Path, int]],
        size: int,
        augment: bool,
        preload: bool = False,
        threads: int = 16,
    ) -> None:
        self.items = list(items)
        self.size = size
        self.augment = augment
        self.cache: list[tuple[np.ndarray, np.ndarray]] | None = None
        if preload:
            with ThreadPoolExecutor(threads) as pool:
                self.cache = list(pool.map(lambda item: load_sample(item[0], size), self.items))

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor, float, int]:
        """(6겹 지도 0~255, 정답 그림, 밝기 배수, 출처 번호). 밝기는 to_input이 GPU에서 곱한다."""
        folder, source = self.items[index]
        if self.cache is None:
            maps, label = load_sample(folder, self.size)
        else:
            maps, label = self.cache[index]
        gain = 1.0
        if self.augment:
            if random.random() < 0.5:
                maps, label = maps[:, :, ::-1], label[:, ::-1]
            gain = 1 + random.uniform(-BRIGHTNESS, BRIGHTNESS)
        return (
            torch.from_numpy(np.ascontiguousarray(maps)),
            torch.from_numpy(np.ascontiguousarray(label)),
            gain,
            source,
        )


def block(inputs: int, outputs: int) -> nn.Sequential:
    """3×3 합성곱 두 번. 묶음이 작아도 흔들리지 않게 GroupNorm을 쓴다."""
    layers: list[nn.Module] = []
    for channels in (inputs, outputs):
        layers += [
            nn.Conv2d(channels, outputs, kernel_size=3, padding=1, bias=False),
            nn.GroupNorm(GROUPS, outputs),
            nn.ReLU(inplace=True),
        ]
    return nn.Sequential(*layers)


class SmallNet(nn.Module):
    """처음부터 학습하는 작은 모델. 줄이며 내려갔다가 같은 크기 층을 이어 붙이며 올라온다(U-Net)."""

    def __init__(self, inputs: int = 6, classes: int = NUM_CLASSES) -> None:
        super().__init__()
        widths = SMALL_WIDTHS
        self.down = nn.ModuleList(
            block(a, b) for a, b in zip((inputs, *widths[:-1]), widths, strict=True)
        )
        self.up = nn.ModuleList(
            block(a + b, b) for a, b in zip(widths[:0:-1], widths[-2::-1], strict=True)
        )
        self.out = nn.Conv2d(widths[0], classes, kernel_size=1)

    def forward(self, x: Tensor) -> tuple[Tensor]:
        kept = []
        for index, layer in enumerate(self.down):
            x = layer(x if index == 0 else F.max_pool2d(x, 2))
            kept.append(x)
        for layer, skip in zip(self.up, kept[-2::-1], strict=True):
            x = F.interpolate(x, size=skip.shape[2:], mode="bilinear", align_corners=False)
            x = layer(torch.cat([x, skip], dim=1))
        return (self.out(x),)


def widen_input(conv: nn.Conv2d) -> nn.Conv2d:
    """3겹을 받던 첫 층을 6겹(직전 3 + 직후 3)으로 늘린다.

    전·후에 원래 가중치를 반씩 넣는다. 전후가 같은 그림이면 원래 모델과 같은 값이 나온다.
    """
    new = nn.Conv2d(
        2 * conv.in_channels,
        conv.out_channels,
        kernel_size=conv.kernel_size,
        stride=conv.stride,
        padding=conv.padding,
        bias=False,
    )
    with torch.no_grad():
        new.weight.copy_(torch.cat([conv.weight, conv.weight], dim=1) / 2)
    return new


def reshape_bisenet(model: BiSeNet) -> BiSeNet:
    """BiSeNet의 입력을 6겹으로, 세 출력 머리를 자리 번호 수로 바꾼다. 머리는 새로 시작한다."""
    model.fpn.backbone.conv1 = widen_input(model.fpn.backbone.conv1)
    for head in (model.conv_out, model.conv_out16, model.conv_out32):
        head.conv = nn.Conv2d(head.conv.in_channels, NUM_CLASSES, kernel_size=1, bias=False)
    return model


def build_model(name: str, pretrained: Path | None = BISENET_PT) -> nn.Module:
    """출발 모델. bisenet은 pretrained(얼굴 분할 가중치)에서 출발하고 None이면 처음부터다."""
    if name == "small":
        return SmallNet()
    model = BiSeNet(19, "resnet18")
    if pretrained is not None:
        model.load_state_dict(
            torch.load(pretrained, map_location="cpu", weights_only=True), strict=True
        )
    return reshape_bisenet(model)


def load_trained(name: str, checkpoint: Path, device: str) -> nn.Module:
    """학습한 가중치(best.pt)를 불러 평가 모드로 둔 모델."""
    model = build_model(name, pretrained=None)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
    return model.to(device).eval()


def train_mode(model: nn.Module, freeze_bn: bool) -> None:
    """학습 모드로 둔다. freeze_bn이면 BatchNorm 통계는 원본 그대로 둔다(작은 묶음에서 흔들려서)."""
    model.train()
    if freeze_bn:
        for module in model.modules():
            if isinstance(module, nn.BatchNorm2d):
                module.eval()


def class_weights(painted_weight: float, device: str) -> Tensor:
    """안 바름은 1, 바른 자리는 모두 painted_weight인 손실 가중치."""
    weights = torch.full((NUM_CLASSES,), painted_weight, device=device)
    weights[0] = 1.0
    return weights


def loss_fn(outputs: Sequence[Tensor], label: Tensor, weights: Tensor) -> Tensor:
    """주 출력과 보조 출력(AUX_WEIGHT배)의 가중 교차 엔트로피 합. 모름 칸은 뺀다."""
    total = F.cross_entropy(outputs[0], label, weight=weights, ignore_index=labels.IGNORE)
    for aux in outputs[1:]:
        total = total + AUX_WEIGHT * F.cross_entropy(
            aux, label, weight=weights, ignore_index=labels.IGNORE
        )
    return total


def overlap_cells(pred: Tensor, label: Tensor) -> tuple[Tensor, Tensor]:
    """바른 자리마다 (맞게 칠한 칸 수, 예측이나 정답이 칠한 칸 수). 모름 칸은 세지 않는다."""
    valid = label != labels.IGNORE
    both, either = [], []
    for number in PAINTED:
        guessed, truth = (pred == number) & valid, (label == number) & valid
        both.append((guessed & truth).sum())
        either.append((guessed | truth).sum())
    return torch.stack(both), torch.stack(either)


def score(both: np.ndarray, either: np.ndarray, wrong: int, clean: int) -> dict:
    """칸 수에서 자리별 IoU, 그 평균, 아무것도 안 바른 정답지에서 바름으로 칠한 비율을 낸다.

    검증에 한 번도 안 나오고 예측도 안 한 자리는 IoU가 None이고 평균에서 뺀다.
    """
    each = {
        name: (float(b) / float(e) if e > 0 else None)
        for name, b, e in zip(labels.CLASSES[1:], both, either, strict=True)
    }
    seen = [value for value in each.values() if value is not None]
    return {
        "meanIoU": sum(seen) / len(seen) if seen else 0.0,
        "classIoU": each,
        "cleanFalsePositive": wrong / clean if clean else None,
    }


@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader, device: str) -> dict:
    """검증 점수. 전체(all)와 출처별(real·synth)로 낸다."""
    model.eval()
    names = ("all", *SOURCES)
    both = {name: np.zeros(len(PAINTED)) for name in names}
    either = {name: np.zeros(len(PAINTED)) for name in names}
    wrong = dict.fromkeys(names, 0)
    clean = dict.fromkeys(names, 0)
    for maps, label, gains, source in loader:
        image = to_input(maps, gains, device)
        label = label.to(device).long()
        with torch.autocast(device, dtype=torch.float16, enabled=device == "cuda"):
            pred = model(image)[0].argmax(1)
        for one_pred, one_label, one_source in zip(pred, label, source.tolist(), strict=True):
            b, e = overlap_cells(one_pred, one_label)
            valid = one_label != labels.IGNORE
            bare = not torch.isin(one_label, torch.tensor(PAINTED, device=device)).any()
            for name in ("all", SOURCES[one_source]):
                both[name] += b.cpu().numpy()
                either[name] += e.cpu().numpy()
                if bare:
                    wrong[name] += int(((one_pred > 0) & valid).sum())
                    clean[name] += int(valid.sum())
    return {name: score(both[name], either[name], wrong[name], clean[name]) for name in names}


def real_count(step: int, batch: int, real_share: float, real: int, synth: int) -> int:
    """step번째 묶음(0부터)에 넣을 실제 장면 건수. 나머지는 합성이다.

    여러 묶음에 걸쳐 실제 장면이 batch × real_share 비율이 되게 나눈다. 비율 0.125에 묶음 4건이면
    두 묶음에 한 건이다. 한쪽 정답지가 없으면 있는 쪽으로 다 채운다.
    """
    if real == 0:
        return 0
    if synth == 0:
        return batch
    share = batch * real_share
    return min(batch, int((step + 1) * share + 1e-9) - int(step * share + 1e-9))


def lr_scale(step: int, total: int, schedule: str) -> float:
    """step번째 걸음(0부터)의 학습률 배수. 처음 WARMUP_STEPS 걸음은 0에서 1로 올린다.

    schedule이 constant면 그 뒤로 1이고, cosine이면 total 걸음에 걸쳐 1에서 0으로 코사인처럼 줄인다.
    끝으로 갈수록 덜 움직여 에폭마다 점수가 오르내리는 것을 줄이려는 것이다.
    """
    scale = min(1.0, (step + 1) / WARMUP_STEPS)
    if schedule == "cosine":
        scale *= 0.5 * (1 + math.cos(math.pi * min(1.0, step / max(1, total))))
    return scale


def endless(loader: DataLoader | None) -> Iterator:
    """묶음을 끝없이 낸다. 한 바퀴가 끝나면 다시 섞어 돈다."""
    while loader is not None:
        yield from loader


def read_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run")
    parser.add_argument("--model", choices=("bisenet", "small"), default="bisenet")
    parser.add_argument("--painted-weight", type=float, default=3.0)
    parser.add_argument("--real-share", type=float, default=0.5)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--validation-split", choices=workspace.SPLITS[:2], default="validation")
    parser.add_argument("--scratch", action="store_true", help="bisenet을 가중치 없이 시작")
    parser.add_argument("--seed", type=int, default=SEED, help="같은 설정의 흔들림을 볼 때 바꿈")
    parser.add_argument("--schedule", choices=("constant", "cosine"), default="constant")
    parser.add_argument("--preload", action="store_true", help="정답지를 처음에 메모리에 다 올림")
    return parser.parse_args()


def main() -> None:
    args = read_args()
    run_dir = RUNS_DIR / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    train = {source: sample_folders("train", source) for source in SOURCES}
    val_items = [
        (folder, number)
        for number, source in enumerate(SOURCES)
        for folder in sample_folders(args.validation_split, source)
    ]
    sizes = (len(train["real"]), len(train["synth"]))
    steps_per_epoch = max(1, sum(sizes) // args.batch)
    used = (
        sizes[0] > 0 and (sizes[1] == 0 or args.real_share > 0),
        sizes[1] > 0 and (sizes[0] == 0 or args.real_share < 1),
    )
    loaders = []
    for number, (source, batch) in enumerate(zip(SOURCES, (1, args.batch), strict=True)):
        if not used[number]:
            loaders.append(None)
            continue
        workers = min(args.workers, 1) if source == "real" else args.workers
        loaders.append(
            DataLoader(
                Pairs(
                    [(folder, number) for folder in train[source]],
                    args.size,
                    augment=True,
                    preload=args.preload,
                ),
                batch_size=batch,
                shuffle=True,
                drop_last=len(train[source]) >= batch,
                num_workers=workers,
                persistent_workers=workers > 0,
                pin_memory=True,
            )
        )
    val_loader = DataLoader(
        Pairs(val_items, args.size, augment=False, preload=args.preload),
        batch_size=VAL_BATCH,
        shuffle=False,
        num_workers=args.workers,
        persistent_workers=args.workers > 0,
    )

    pretrained = None if args.scratch else BISENET_PT
    model = build_model(args.model, pretrained).to(device)
    freeze_bn = args.model == "bisenet" and pretrained is not None
    if args.model == "bisenet":
        backbone = list(model.fpn.backbone.parameters())
        backbone_ids = {id(p) for p in backbone}
        head = [p for p in model.parameters() if id(p) not in backbone_ids]
        groups = [
            {"params": backbone, "lr": args.lr * BACKBONE_LR_SHARE},
            {"params": head, "lr": args.lr},
        ]
    else:
        groups = [{"params": list(model.parameters()), "lr": args.lr}]
    optimizer = torch.optim.AdamW(groups, weight_decay=WEIGHT_DECAY)
    scaler = torch.amp.GradScaler(device, enabled=device == "cuda")
    weights = class_weights(args.painted_weight, device)

    log = {
        "settings": vars(args),
        "pretrained": pretrained is not None and args.model == "bisenet",
        "trainReal": len(train["real"]),
        "trainSynth": len(train["synth"]),
        "validation": len(val_items),
        "stepsPerEpoch": steps_per_epoch,
        "parameters": sum(p.numel() for p in model.parameters()),
        "epochs": [],
    }
    print(json.dumps({k: v for k, v in log.items() if k != "epochs"}, ensure_ascii=False))
    log["beforeTraining"] = evaluate(model, val_loader, device)
    print("학습 전", log["beforeTraining"]["all"], flush=True)

    real_stream, synth_stream = (endless(loader) for loader in loaders)
    best, bad_epochs, step = -1.0, 0, 0
    base_lrs = [group["lr"] for group in optimizer.param_groups]
    for epoch in range(1, args.epochs + 1):
        train_mode(model, freeze_bn)
        started, running, done = time.time(), 0.0, 0
        for _ in range(steps_per_epoch):
            scale = lr_scale(step, args.epochs * steps_per_epoch, args.schedule)
            for group, lr in zip(optimizer.param_groups, base_lrs, strict=True):
                group["lr"] = lr * scale
            reals = real_count(step, args.batch, args.real_share, *sizes)
            parts = [next(real_stream) for _ in range(reals)]
            if reals < args.batch:
                synth = next(synth_stream)
                keep = args.batch - reals
                parts.append(tuple(item[:keep] for item in synth[:3]))
            image = to_input(
                torch.cat([part[0] for part in parts]),
                torch.cat([part[2] for part in parts]),
                device,
            )
            label = torch.cat([part[1] for part in parts]).to(device, non_blocking=True).long()
            with torch.autocast(device, dtype=torch.float16, enabled=device == "cuda"):
                loss = loss_fn(model(image), label, weights)
            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running += loss.item()
            step += 1
            done += 1
            if args.max_steps and step >= args.max_steps:
                break
        train_sec = time.time() - started
        result = evaluate(model, val_loader, device)
        row = {
            "epoch": epoch,
            "loss": running / done,
            "trainSec": round(train_sec, 1),
            "secPerStep": round(train_sec / done, 3),
            "gpuPeakMB": (
                round(torch.cuda.max_memory_allocated() / 2**20) if device == "cuda" else None
            ),
            **result,
        }
        log["epochs"].append(row)
        print(
            {key: row[key] for key in ("epoch", "loss", "trainSec", "secPerStep", "gpuPeakMB")},
            result["all"],
            flush=True,
        )
        if result["all"]["meanIoU"] > best:
            best, bad_epochs = result["all"]["meanIoU"], 0
            torch.save(model.state_dict(), run_dir / "best.pt")
            log["best"] = row
        else:
            bad_epochs += 1
        workspace.write_json(run_dir / "log.json", log)
        if bad_epochs >= args.patience or (args.max_steps and step >= args.max_steps):
            break
    log["finished"] = True
    workspace.write_json(run_dir / "log.json", log)
    print("가장 좋은 에폭", log.get("best", {}).get("epoch"), best, flush=True)


if __name__ == "__main__":
    main()
