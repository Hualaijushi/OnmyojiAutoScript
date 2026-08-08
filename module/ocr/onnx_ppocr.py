import math
import threading
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import pyclipper
import yaml

from module.ocr.common import BoxedResult, OcrLogger
from module.ocr.model_manager import normalize_variant, resolve_model_files


_SESSION_CACHE: dict[tuple, ort.InferenceSession] = {}
_SESSION_CACHE_LOCK = threading.Lock()
_REC_IMAGE_HEIGHT = 48
_REC_MAX_IMAGE_WIDTH = 3200


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _create_session(
    path: Path,
    providers: tuple[str, ...],
    intra_op_threads: int,
    inter_op_threads: int,
) -> ort.InferenceSession:
    key = (str(path.resolve()), providers, intra_op_threads, inter_op_threads)
    session = _SESSION_CACHE.get(key)
    if session is not None:
        return session

    with _SESSION_CACHE_LOCK:
        session = _SESSION_CACHE.get(key)
        if session is not None:
            return session
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, int(intra_op_threads))
        options.inter_op_num_threads = max(1, int(inter_op_threads))
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(
            str(path),
            sess_options=options,
            providers=list(providers),
        )
        _SESSION_CACHE[key] = session
        return session


def _det_resize(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height, width = image.shape[:2]
    if not height or not width:
        raise ValueError("OCR image must not be empty")

    limit_side_len = 64
    ratio = float(limit_side_len) / min(height, width) if min(height, width) < limit_side_len else 1.0
    resize_height = int(height * ratio)
    resize_width = int(width * ratio)
    if max(resize_height, resize_width) > 4000:
        max_ratio = 4000.0 / max(resize_height, resize_width)
        resize_height = int(resize_height * max_ratio)
        resize_width = int(resize_width * max_ratio)

    resize_height = max(int(round(resize_height / 32) * 32), 32)
    resize_width = max(int(round(resize_width / 32) * 32), 32)
    resized = image if (resize_height, resize_width) == (height, width) else cv2.resize(
        image, (resize_width, resize_height)
    )
    shape = np.array(
        [height, width, resize_height / float(height), resize_width / float(width)],
        dtype=np.float32,
    )
    return resized, shape


def _det_preprocess(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    image, shape = _det_resize(image)
    image = image.astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)
    image = (image - mean) / std
    return np.expand_dims(image.transpose((2, 0, 1)), axis=0), shape


def _box_score(bitmap: np.ndarray, box: np.ndarray) -> float:
    height, width = bitmap.shape[:2]
    box = box.copy()
    xmin = max(0, min(math.floor(box[:, 0].min()), width - 1))
    xmax = max(0, min(math.ceil(box[:, 0].max()), width - 1))
    ymin = max(0, min(math.floor(box[:, 1].min()), height - 1))
    ymax = max(0, min(math.ceil(box[:, 1].max()), height - 1))
    mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
    box[:, 0] -= xmin
    box[:, 1] -= ymin
    cv2.fillPoly(mask, box.reshape(1, -1, 2).astype(np.int32), 1)
    return float(cv2.mean(bitmap[ymin:ymax + 1, xmin:xmax + 1], mask)[0])


def _mini_box(contour: np.ndarray) -> tuple[np.ndarray, float]:
    rectangle = cv2.minAreaRect(contour)
    points = sorted(cv2.boxPoints(rectangle).tolist(), key=lambda point: point[0])
    if points[1][1] > points[0][1]:
        bottom_left, top_left = points[1], points[0]
    else:
        bottom_left, top_left = points[0], points[1]
    if points[3][1] > points[2][1]:
        bottom_right, top_right = points[3], points[2]
    else:
        bottom_right, top_right = points[2], points[3]
    return np.array([top_left, top_right, bottom_right, bottom_left]), min(rectangle[1])


def _unclip(box: np.ndarray, ratio: float) -> np.ndarray | None:
    perimeter = cv2.arcLength(box.astype(np.float32), True)
    if perimeter <= 0:
        return None
    distance = cv2.contourArea(box.astype(np.float32)) * ratio / perimeter
    offset = pyclipper.PyclipperOffset()
    offset.AddPath(box.astype(np.int32).tolist(), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    expanded = offset.Execute(distance)
    if not expanded:
        return None
    return np.array(max(expanded, key=lambda item: cv2.contourArea(np.asarray(item))), dtype=np.float32)


def _det_postprocess(
    prediction: np.ndarray,
    shape: np.ndarray,
    threshold: float,
    box_threshold: float,
    unclip_ratio: float,
    max_candidates: int,
) -> list[np.ndarray]:
    probability = prediction[0, 0]
    bitmap = probability > threshold
    source_height, source_width = shape[:2]
    height, width = bitmap.shape
    contours, _ = cv2.findContours(
        (bitmap * 255).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    boxes = []
    for contour in contours[:max_candidates]:
        box, short_side = _mini_box(contour)
        if short_side < 3 or _box_score(probability, box) < box_threshold:
            continue
        expanded = _unclip(box, unclip_ratio)
        if expanded is None:
            continue
        box, short_side = _mini_box(expanded.reshape(-1, 1, 2))
        if short_side < 5:
            continue
        box[:, 0] = np.clip(np.round(box[:, 0] * source_width / width), 0, source_width)
        box[:, 1] = np.clip(np.round(box[:, 1] * source_height / height), 0, source_height)
        boxes.append(box.astype(np.int32))
    return sorted(boxes, key=lambda item: (item[:, 1].min(), item[:, 0].min()))


def _crop_text(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    crop_width = max(
        int(np.linalg.norm(points[0] - points[1])),
        int(np.linalg.norm(points[2] - points[3])),
        1,
    )
    crop_height = max(
        int(np.linalg.norm(points[0] - points[3])),
        int(np.linalg.norm(points[1] - points[2])),
        1,
    )
    destination = np.float32(
        [[0, 0], [crop_width, 0], [crop_width, crop_height], [0, crop_height]]
    )
    matrix = cv2.getPerspectiveTransform(points.astype(np.float32), destination)
    cropped = cv2.warpPerspective(
        image,
        matrix,
        (crop_width, crop_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    if cropped.shape[0] / float(max(cropped.shape[1], 1)) >= 1.5:
        cropped = np.rot90(cropped)
    return cropped


def _rec_preprocess(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    if not height or not width:
        raise ValueError("OCR text crop must not be empty")
    max_ratio = max(320 / 48, width / float(height))
    target_width = min(int(_REC_IMAGE_HEIGHT * max_ratio), _REC_MAX_IMAGE_WIDTH)
    resized_width = min(int(math.ceil(_REC_IMAGE_HEIGHT * width / float(height))), target_width)
    resized = cv2.resize(image, (resized_width, _REC_IMAGE_HEIGHT)).astype(np.float32)
    resized = (resized.transpose((2, 0, 1)) / 255.0 - 0.5) / 0.5
    padded = np.zeros((3, _REC_IMAGE_HEIGHT, target_width), dtype=np.float32)
    padded[:, :, :resized_width] = resized
    return np.expand_dims(padded, axis=0)


def _ctc_decode(output: np.ndarray, characters: list[str]) -> tuple[str, float]:
    indices = output[0].argmax(axis=-1)
    probabilities = output[0].max(axis=-1)
    selection = np.ones(len(indices), dtype=bool)
    selection[1:] = indices[1:] != indices[:-1]
    selection &= indices != 0
    valid_indices = indices[selection]
    text = "".join(characters[index] for index in valid_indices if index < len(characters))
    confidence = probabilities[selection]
    return text, float(np.mean(confidence)) if len(confidence) else 0.0


class TextSystem:
    """Lightweight PP-OCRv6 det/rec pipeline backed directly by ONNX Runtime."""

    def __init__(
        self,
        use_angle_cls: bool = False,
        box_thresh: float | None = 0.8,
        unclip_ratio: float | None = 1.6,
        rec_model_path=None,
        det_model_path=None,
        ort_providers=None,
        model_variant: str = "small",
        intra_op_threads: int = 2,
        inter_op_threads: int = 1,
        **_kwargs,
    ) -> None:
        self.model_variant = normalize_variant(model_variant)
        self._use_angle_cls = use_angle_cls
        providers = tuple(ort_providers or ("CPUExecutionProvider",))

        resolved_det, det_config_path = resolve_model_files(self.model_variant, "det")
        resolved_rec, rec_config_path = resolve_model_files(self.model_variant, "rec")
        det_path = Path(det_model_path) if det_model_path else resolved_det
        rec_path = Path(rec_model_path) if rec_model_path else resolved_rec
        self._det_session = _create_session(
            det_path, providers, intra_op_threads, inter_op_threads
        )
        self._rec_session = _create_session(
            rec_path, providers, intra_op_threads, inter_op_threads
        )
        self._det_input = self._det_session.get_inputs()[0].name
        self._rec_input = self._rec_session.get_inputs()[0].name

        det_config = _load_yaml(det_config_path).get("PostProcess", {})
        rec_config = _load_yaml(rec_config_path).get("PostProcess", {})
        self._threshold = float(det_config.get("thresh", 0.3))
        self._box_threshold = float(
            det_config.get("box_thresh", 0.6) if box_thresh is None else box_thresh
        )
        self._unclip_ratio = float(
            det_config.get("unclip_ratio", 1.5) if unclip_ratio is None else unclip_ratio
        )
        self._max_candidates = int(det_config.get("max_candidates", 3000))
        self._characters = ["blank"] + list(rec_config.get("character_dict", [])) + [" "]
        self.text_recognizer = None

    def recognize_batch(self, images: list[np.ndarray]) -> list[tuple[str, float]]:
        return [self._recognize(image) for image in images]

    def _recognize(self, image: np.ndarray) -> tuple[str, float]:
        tensor = _rec_preprocess(image)
        output = self._rec_session.run(None, {self._rec_input: tensor})[0]
        return _ctc_decode(output, self._characters)

    def ocr_single_line(self, image: np.ndarray) -> tuple[str, float]:
        text, score = self._recognize(image)
        OcrLogger.save(image, "ocr_single_line", text, score)
        return text, score

    def detect_and_ocr(
        self,
        image: np.ndarray,
        drop_score: float = 0.5,
        unclip_ratio: float | None = None,
        box_thresh: float | None = None,
    ) -> list[BoxedResult]:
        tensor, shape = _det_preprocess(image)
        prediction = self._det_session.run(None, {self._det_input: tensor})[0]
        boxes = _det_postprocess(
            prediction,
            shape,
            self._threshold,
            self._box_threshold if box_thresh is None else float(box_thresh),
            self._unclip_ratio if unclip_ratio is None else float(unclip_ratio),
            self._max_candidates,
        )
        crops = [_crop_text(image, box) for box in boxes]
        recognizer = self.text_recognizer or self.recognize_batch
        recognized = recognizer(crops)
        results = [
            BoxedResult(box, crop, text, float(score))
            for box, crop, (text, score) in zip(boxes, crops, recognized)
            if float(score) >= drop_score
        ]
        pairs = [(item.ocr_text, item.score) for item in results]
        if pairs:
            OcrLogger.save(image, "detect_and_ocr", pairs[0][0], pairs[0][1], pairs=pairs)
        else:
            OcrLogger.save(image, "detect_and_ocr", "", 0.0, extra="no_result")
        return results
