import os
import subprocess
import sys
from pathlib import Path

from module.logger import logger


SUPPORTED_VARIANTS = {"small", "medium"}


def normalize_variant(variant: str) -> str:
    variant = str(variant or "small").lower()
    if variant not in SUPPORTED_VARIANTS:
        raise ValueError(f"Unsupported OCR model variant: {variant}")
    return variant


def _cache_root() -> Path:
    configured = os.environ.get("PADDLE_PDX_CACHE_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".paddlex"


def _model_directory(model_name: str) -> Path:
    return _cache_root() / "official_models" / f"{model_name}_onnx"


def _download_official_onnx_model(model_name: str) -> None:
    """Download through PaddleX in a child process so downloader imports are released."""
    script = (
        "from paddlex.inference.utils.official_models import official_models; "
        f"print(official_models.get_model_path({model_name!r}, model_formats=['onnx']))"
    )
    logger.info(f"Downloading official OCR model: {model_name}_onnx")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"Failed to download {model_name}_onnx: {detail}")
    if completed.stdout.strip():
        logger.info(completed.stdout.strip().splitlines()[-1])


def resolve_model_files(variant: str, role: str) -> tuple[Path, Path]:
    variant = normalize_variant(variant)
    role = str(role).lower()
    if role not in {"det", "rec"}:
        raise ValueError(f"Unsupported OCR model role: {role}")

    model_name = f"PP-OCRv6_{variant}_{role}"
    model_dir = _model_directory(model_name)
    onnx_path = model_dir / "inference.onnx"
    config_path = model_dir / "inference.yml"
    if not onnx_path.is_file() or not config_path.is_file():
        _download_official_onnx_model(model_name)
    if not onnx_path.is_file() or not config_path.is_file():
        raise FileNotFoundError(
            f"Incomplete OCR model cache for {model_name}: expected {onnx_path} and {config_path}"
        )
    return onnx_path, config_path
