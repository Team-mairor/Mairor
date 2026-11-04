"""BiSeNet(얼굴 부위 19가지)이 가림(19번)도 칠하도록 이어서 학습한다(개발용, GPU).

원본 얼굴 분할 가중치에서 출발해 세 출력 머리를 19칸에서 20칸으로 늘린다(widen).
묶음마다 절반은 진짜 사진 정답지, 절반은 합성 문제다. 에폭마다 검증(다른 사람 영상)을 재서
에폭별 가중치(epoch_NN.pt)와 가림 IoU가 가장 높은 가중치(best.pt), 기록(log.json)을 남긴다.
시험 나눔은 여기서 읽지 않는다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/occlusion_training/train.py \
    <가림 칸 손실 가중치> <결과 폴더> [최대 걸음]
학습 패키지는 train 묶음이다(uv sync --group train).
"""

import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from face_parsing.bisenet import BiSeNet
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset
from workspace import BISENET_PT, REAL_DIR, SYNTH_DIR

SEED = 287
BATCH_REAL = 4
BATCH_SYNTH = 4
MAX_EPOCHS = 15
PATIENCE = 3
LR_BACKBONE = 1e-5
LR_HEAD = 1e-4
WEIGHT_DECAY = 1e-4
AUX_WEIGHT = 0.4
WARMUP_STEPS = 300
FREEZE_BN = True
NUM_WORKERS = 4
BRIGHTNESS = 0.15
FACE_MIN = 0.05
OCCLUDER = 19
IGNORE = 255
NUM_CLASSES = 20
FACE_PARTS = tuple(range(1, 14))
FLIP_PAIRS = ((2, 3), (4, 5), (7, 8))
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def real_items(split):
    """진짜 사진 (사진, 정답지) 목록. 얼굴 칸이 FACE_MIN보다 적은 사진은 뺀다."""
    items = []
    for index_path in sorted((REAL_DIR / split).glob("*/index.json")):
        folder = index_path.parent
        for row in json.loads(index_path.read_text(encoding="utf-8")):
            if row["dropped"] is not None:
                continue
            name = f"{row['frameIndex']:06d}.png"
            label = np.asarray(Image.open(folder / "labels" / name))
            if np.isin(label, (*FACE_PARTS, OCCLUDER)).mean() >= FACE_MIN:
                items.append((folder / "images" / name, folder / "labels" / name))
    return items


def synth_items(split):
    """합성 문제 (사진, 정답지, 아무것도 안 붙였는지) 목록."""
    folder = SYNTH_DIR / split
    lines = (folder / "list.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    return [
        (folder / "images" / r["name"], folder / "labels" / r["name"], not r["items"]) for r in rows
    ]


class Sheets(Dataset):
    """사진과 정답지 묶음. augment면 좌우 뒤집기(좌우 부위 번호도 바꿈)와 밝기 변화를 준다."""

    def __init__(self, items, augment):
        self.items = items
        self.augment = augment

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        image = np.asarray(Image.open(self.items[i][0]).convert("RGB")).astype(np.float32) / 255
        label = np.asarray(Image.open(self.items[i][1])).astype(np.int64)
        if self.augment:
            if random.random() < 0.5:
                image = image[:, ::-1]
                label = label[:, ::-1].copy()
                for a, b in FLIP_PAIRS:
                    swap_a, swap_b = label == a, label == b
                    label[swap_a], label[swap_b] = b, a
            image = np.clip(image * (1 + random.uniform(-BRIGHTNESS, BRIGHTNESS)), 0, 1)
        image = ((image - MEAN) / STD).transpose(2, 0, 1)
        return (
            torch.from_numpy(np.ascontiguousarray(image)),
            torch.from_numpy(np.ascontiguousarray(label)),
        )


def widen(model):
    """세 출력 머리를 19칸에서 20칸으로 늘린다.

    학습된 19칸은 그대로 두고 가림 칸은 0에서 시작한다.
    """
    for head in (model.conv_out, model.conv_out16, model.conv_out32):
        old = head.conv
        new = nn.Conv2d(old.in_channels, NUM_CLASSES, kernel_size=1, bias=False)
        with torch.no_grad():
            new.weight.zero_()
            new.weight[:19] = old.weight
        head.conv = new
    return model


def build_model():
    """원본 얼굴 분할 가중치를 불러 머리를 늘린 모델."""
    model = BiSeNet(19, "resnet18")
    model.load_state_dict(
        torch.load(BISENET_PT, map_location="cpu", weights_only=True), strict=True
    )
    return widen(model)


def load_trained(checkpoint: Path, device: str):
    """학습한 가중치(epoch_NN.pt·best.pt)를 불러 평가 모드로 둔 모델."""
    model = widen(BiSeNet(19, "resnet18"))
    model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
    return model.to(device).eval()


@torch.no_grad()
def predict_occluder(model, rgb: np.ndarray, device: str) -> np.ndarray:
    """512 정사각형 RGB에서 모델이 가림으로 칠한 픽셀(참·거짓 표). GPU에서는 fp16으로 돌린다."""
    x = ((rgb.astype(np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None]
    t = torch.from_numpy(np.ascontiguousarray(x)).to(device)
    if device == "cuda":
        with torch.autocast("cuda", dtype=torch.float16):
            out = model(t)[0]
    else:
        out = model(t)[0]
    return (out.argmax(1)[0] == OCCLUDER).cpu().numpy()


def train_mode(model):
    """학습 모드로 두되 BatchNorm 통계는 원본 그대로 둔다. 작은 묶음에서는 통계가 흔들려서다."""
    model.train()
    if FREEZE_BN:
        for m in model.modules():
            if isinstance(m, nn.BatchNorm2d):
                m.eval()


def loss_fn(outputs, label, class_weights):
    """주 출력과 두 보조 출력(AUX_WEIGHT배)의 가중 교차 엔트로피 합. IGNORE 칸은 뺀다."""
    main, aux16, aux32 = outputs
    total = F.cross_entropy(main, label, weight=class_weights, ignore_index=IGNORE)
    for aux in (aux16, aux32):
        total = total + AUX_WEIGHT * F.cross_entropy(
            aux, label, weight=class_weights, ignore_index=IGNORE
        )
    return total


@torch.no_grad()
def evaluate(model, loader, device):
    """검증 묶음의 가림 IoU와 얼굴 부위 평균 IoU."""
    model.eval()
    inter = union = 0
    part_inter = np.zeros(len(FACE_PARTS))
    part_union = np.zeros(len(FACE_PARTS))
    for image, label in loader:
        image, label = image.to(device), label.to(device)
        with torch.autocast("cuda", dtype=torch.float16):
            pred = model(image)[0].argmax(1)
        valid = label != IGNORE
        p, t = (pred == OCCLUDER) & valid, (label == OCCLUDER) & valid
        inter += (p & t).sum().item()
        union += (p | t).sum().item()
        for k, c in enumerate(FACE_PARTS):
            pc, tc = (pred == c) & valid, (label == c) & valid
            part_inter[k] += (pc & tc).sum().item()
            part_union[k] += (pc | tc).sum().item()
    seen = part_union > 0
    return {
        "occluderIoU": inter / max(1, union),
        "partsMeanIoU": float((part_inter[seen] / part_union[seen]).mean()),
    }


@torch.no_grad()
def clean_false_positive(model, items, device):
    """아무것도 안 붙인 합성 문제에서 얼굴 칸을 가림으로 칠한 비율."""
    model.eval()
    painted = total = 0
    for image_path, label_path in items:
        image, label = Sheets([(image_path, label_path)], augment=False)[0]
        with torch.autocast("cuda", dtype=torch.float16):
            pred = model(image[None].to(device))[0].argmax(1)[0].cpu()
        face = torch.isin(label, torch.tensor(FACE_PARTS))
        painted += ((pred == OCCLUDER) & face).sum().item()
        total += face.sum().item()
    return painted / max(1, total)


def main():
    occluder_weight = float(sys.argv[1])
    run_dir = Path(sys.argv[2])
    max_steps = int(sys.argv[3]) if len(sys.argv) > 3 else None
    run_dir.mkdir(parents=True, exist_ok=True)
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    device = "cuda"

    real_train = real_items("train")
    synth_train = [(i, lbl) for i, lbl, _ in synth_items("train")]
    val_items = real_items("val") + [(i, lbl) for i, lbl, _ in synth_items("val")]
    val_clean = [(i, lbl) for i, lbl, clean in synth_items("val") if clean]
    steps_per_epoch = (len(real_train) + len(synth_train)) // (BATCH_REAL + BATCH_SYNTH)
    loader = {"drop_last": True, "num_workers": NUM_WORKERS, "persistent_workers": True}
    real_loader = DataLoader(
        Sheets(real_train, True), batch_size=BATCH_REAL, shuffle=True, pin_memory=True, **loader
    )
    synth_loader = DataLoader(
        Sheets(synth_train, True), batch_size=BATCH_SYNTH, shuffle=True, pin_memory=True, **loader
    )
    val_loader = DataLoader(
        Sheets(val_items, False), batch_size=8, shuffle=False, num_workers=NUM_WORKERS
    )

    model = build_model().to(device)
    backbone = list(model.fpn.backbone.parameters())
    backbone_ids = {id(p) for p in backbone}
    head = [p for p in model.parameters() if id(p) not in backbone_ids]
    optimizer = torch.optim.AdamW(
        [{"params": backbone, "lr": LR_BACKBONE}, {"params": head, "lr": LR_HEAD}],
        weight_decay=WEIGHT_DECAY,
    )
    scaler = torch.amp.GradScaler("cuda")
    class_weights = torch.ones(NUM_CLASSES, device=device)
    class_weights[OCCLUDER] = occluder_weight

    log = {
        "occluderWeight": occluder_weight,
        "realTrain": len(real_train),
        "synthTrain": len(synth_train),
        "val": len(val_items),
        "valClean": len(val_clean),
        "stepsPerEpoch": steps_per_epoch,
        "epochs": [],
    }
    log["beforeTraining"] = evaluate(model, val_loader, device) | {
        "cleanFalsePositive": clean_false_positive(model, val_clean, device)
    }
    print("학습 전", log["beforeTraining"], flush=True)

    def endless(loader):
        while True:
            yield from loader

    real_iter, synth_iter = endless(real_loader), endless(synth_loader)
    best, bad_epochs, step = -1.0, 0, 0
    base_lrs = [g["lr"] for g in optimizer.param_groups]
    for epoch in range(1, MAX_EPOCHS + 1):
        train_mode(model)
        t0, running = time.time(), 0.0
        for _ in range(steps_per_epoch):
            scale = min(1.0, (step + 1) / WARMUP_STEPS)
            for g, lr in zip(optimizer.param_groups, base_lrs, strict=True):
                g["lr"] = lr * scale
            ri, rl = next(real_iter)
            si, sl = next(synth_iter)
            image = torch.cat([ri, si]).to(device, non_blocking=True)
            label = torch.cat([rl, sl]).to(device, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.float16):
                loss = loss_fn(model(image), label, class_weights)
            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running += loss.item()
            step += 1
            if max_steps and step >= max_steps:
                break
        train_sec = time.time() - t0
        score = evaluate(model, val_loader, device) | {
            "cleanFalsePositive": clean_false_positive(model, val_clean, device)
        }
        row = {
            "epoch": epoch,
            "loss": running / max(1, step if max_steps else steps_per_epoch),
            "trainSec": round(train_sec, 1),
            **score,
        }
        log["epochs"].append(row)
        print(row, flush=True)
        torch.save(model.state_dict(), run_dir / f"epoch_{epoch:02d}.pt")
        if score["occluderIoU"] > best:
            best, bad_epochs = score["occluderIoU"], 0
            torch.save(model.state_dict(), run_dir / "best.pt")
            log["best"] = row
        else:
            bad_epochs += 1
        (run_dir / "log.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        if bad_epochs >= PATIENCE or (max_steps and step >= max_steps):
            break
    print("가장 좋은 에폭", log.get("best"), flush=True)


if __name__ == "__main__":
    main()
