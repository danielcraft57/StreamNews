"""Telechargement d'images + backends de detection faciale (optionnels).

Deps lourdes hors requirements.txt :
  pip install -r requirements-faces.txt
"""
from __future__ import annotations

import io
import logging
import math
import os
import struct
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = float(os.getenv("FACE_DETECT_TIMEOUT", "15"))
_DEFAULT_MAX_BYTES = int(os.getenv("FACE_DETECT_MAX_BYTES", str(5 * 1024 * 1024)))
_DEFAULT_MAX_IMAGES = int(os.getenv("FACE_DETECT_MAX_IMAGES", "5"))

# Seuils de similarite
_FR_DISTANCE_MAX = float(os.getenv("FACE_MATCH_DISTANCE", "0.6"))  # face_recognition (euclidien)
_IF_COSINE_MIN = float(os.getenv("FACE_MATCH_COSINE", "0.35"))  # insightface


def pack_embedding(values: List[float]) -> bytes:
    return struct.pack(f"{len(values)}f", *[float(v) for v in values])


def unpack_embedding(blob: bytes) -> List[float]:
    if not blob:
        return []
    n = len(blob) // 4
    if n < 1:
        return []
    return list(struct.unpack(f"{n}f", blob[: n * 4]))


def embedding_distance(a: List[float], b: List[float], *, metric: str = "euclidean") -> float:
    if not a or not b or len(a) != len(b):
        return float("inf")
    if metric == "cosine":
        # distance = 1 - cosine_similarity
        return 1.0 - _cosine_similarity(a, b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def embeddings_match(
    a: List[float],
    b: List[float],
    *,
    metric: str = "euclidean",
) -> bool:
    if metric == "cosine":
        return _cosine_similarity(a, b) >= _IF_COSINE_MIN
    return embedding_distance(a, b, metric="euclidean") <= _FR_DISTANCE_MAX


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


def download_image_bytes(
    url: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> Optional[bytes]:
    """Telecharge une image (HTTP). Retourne None si echec / trop gros."""
    if not url or not str(url).startswith(("http://", "https://")):
        return None
    try:
        import requests

        with requests.get(
            url,
            timeout=timeout,
            stream=True,
            headers={"User-Agent": "StreamNews-FaceDetect/1.0"},
        ) as resp:
            resp.raise_for_status()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if ctype and not any(
                t in ctype for t in ("image/", "octet-stream", "binary")
            ):
                # certains CDN omettent le type ; on continue quand meme
                if "text/" in ctype or "html" in ctype:
                    return None
            chunks: List[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    logger.info("image trop grande ignoree url=%s size>%s", url[:80], max_bytes)
                    return None
                chunks.append(chunk)
            return b"".join(chunks) if chunks else None
    except Exception as exc:
        logger.debug("download image failed url=%s: %s", url[:80], exc)
        return None


def _rgb_array_from_bytes(data: bytes):
    """PIL -> numpy RGB uint8 (H, W, 3)."""
    from PIL import Image
    import numpy as np

    img = Image.open(io.BytesIO(data))
    if img.mode != "RGB":
        img = img.convert("RGB")
    return np.asarray(img)


def detect_with_face_recognition(
    image_bytes: bytes,
    *,
    media_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Backend face_recognition (dlib) - embedding 128d, distance euclidienne."""
    import face_recognition

    rgb = _rgb_array_from_bytes(image_bytes)
    h, w = int(rgb.shape[0]), int(rgb.shape[1])
    if h < 8 or w < 8:
        return []

    locations = face_recognition.face_locations(rgb, model="hog")
    if not locations:
        return []
    encodings = face_recognition.face_encodings(rgb, known_face_locations=locations)
    faces: List[Dict[str, Any]] = []
    for loc, enc in zip(locations, encodings):
        top, right, bottom, left = loc
        faces.append(
            _face_row(
                media_id=media_id,
                x=left / w,
                y=top / h,
                bw=(right - left) / w,
                bh=(bottom - top) / h,
                confidence=None,
                embedding=pack_embedding([float(v) for v in enc]),
                embedding_dim=len(enc),
                metric="euclidean",
                backend="face_recognition",
            )
        )
    return faces


def detect_with_insightface(
    image_bytes: bytes,
    *,
    media_id: Optional[int] = None,
    app: Any = None,
) -> List[Dict[str, Any]]:
    """Backend InsightFace - embedding ~512d, similarite cosinus."""
    import numpy as np
    import cv2

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        return []
    h, w = int(bgr.shape[0]), int(bgr.shape[1])
    if app is None:
        app = _get_insightface_app()
    detected = app.get(bgr)
    faces: List[Dict[str, Any]] = []
    for face in detected or []:
        bbox = getattr(face, "bbox", None)
        if bbox is None or len(bbox) < 4:
            continue
        x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
        emb = getattr(face, "embedding", None)
        if emb is None:
            continue
        vals = [float(v) for v in emb]
        score = getattr(face, "det_score", None)
        faces.append(
            _face_row(
                media_id=media_id,
                x=x1 / w,
                y=y1 / h,
                bw=(x2 - x1) / w,
                bh=(y2 - y1) / h,
                confidence=float(score) if score is not None else None,
                embedding=pack_embedding(vals),
                embedding_dim=len(vals),
                metric="cosine",
                backend="insightface",
            )
        )
    return faces


_insight_app = None


def _get_insightface_app():
    global _insight_app
    if _insight_app is not None:
        return _insight_app
    from insightface.app import FaceAnalysis

    name = os.getenv("INSIGHTFACE_MODEL", "buffalo_s")
    providers = ["CPUExecutionProvider"]
    app = FaceAnalysis(name=name, providers=providers)
    app.prepare(ctx_id=-1, det_size=(640, 640))
    _insight_app = app
    return app


def _face_row(
    *,
    media_id: Optional[int],
    x: float,
    y: float,
    bw: float,
    bh: float,
    confidence: Optional[float],
    embedding: bytes,
    embedding_dim: int,
    metric: str,
    backend: str,
) -> Dict[str, Any]:
    return {
        "media_id": media_id,
        "bbox": {
            "x": max(0.0, min(1.0, x)),
            "y": max(0.0, min(1.0, y)),
            "w": max(0.0, min(1.0, bw)),
            "h": max(0.0, min(1.0, bh)),
            "unit": "ratio",
        },
        "confidence": confidence,
        "embedding": embedding,
        "embedding_dim": embedding_dim,
        "match_metric": metric,
        "backend": backend,
    }


def run_backend_on_media(
    backend: str,
    media_items: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Telecharge et detecte sur une liste de media image.

    Retourne (faces, errors).
    """
    backend = (backend or "").strip().lower()
    max_images = max(1, _DEFAULT_MAX_IMAGES)
    faces: List[Dict[str, Any]] = []
    errors: List[str] = []
    processed = 0

    for item in media_items:
        if processed >= max_images:
            break
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        media_type = (item.get("media_type") or "image").lower()
        if media_type not in ("image", "img", ""):
            continue
        data = download_image_bytes(url)
        processed += 1
        if not data:
            errors.append(f"download failed: {url[:60]}")
            continue
        media_id = item.get("media_id") or item.get("id")
        if not isinstance(media_id, int):
            media_id = None
        try:
            if backend in ("face_recognition", "dlib"):
                found = detect_with_face_recognition(data, media_id=media_id)
            elif backend == "insightface":
                found = detect_with_insightface(data, media_id=media_id)
            else:
                errors.append(f"backend inconnu: {backend}")
                break
            faces.extend(found)
        except Exception as exc:
            errors.append(f"{url[:40]}: {exc}")
            logger.warning("face detect failed url=%s: %s", url[:80], exc)

    return faces, errors
