"""Detection / reco faciale optionnelle (tool_name=face_detect).

Desactivee par defaut. Activer :
  FACE_DETECT_ENABLED=1
  FACE_DETECT_BACKEND=face_recognition   # ou insightface

Deps : pip install -r analyzer/requirements-faces.txt
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from text_analysis.base import error_result, ok_result, skip_result


def face_detect_enabled() -> bool:
    raw = (os.getenv("FACE_DETECT_ENABLED") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def face_detect_backend() -> str:
    return (os.getenv("FACE_DETECT_BACKEND") or "stub").strip().lower()


class FaceDetectAnalyzer:
    """Analyseur enregistre dans le runner (tool_name=face_detect)."""

    name = "face_detect"

    def is_available(self) -> bool:
        """True si on peut tenter une analyse (ou renvoyer un skip explicite)."""
        if not face_detect_enabled():
            return True  # analyze() renvoie skipped avec message clair
        backend = face_detect_backend()
        if backend in ("", "stub", "none", "off"):
            return True
        if backend == "insightface":
            try:
                import insightface  # noqa: F401
                import cv2  # noqa: F401
                return True
            except ImportError:
                return False
        if backend in ("face_recognition", "dlib"):
            try:
                import face_recognition  # noqa: F401
                from PIL import Image  # noqa: F401
                import numpy  # noqa: F401
                return True
            except ImportError:
                return False
        return False

    def analyze(
        self,
        text: str,
        *,
        lang_hint: Optional[str] = None,
        media_urls: Optional[List[str]] = None,
        media_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if not face_detect_enabled():
            return skip_result(
                "face_detect desactive (FACE_DETECT_ENABLED=0) ; "
                "optionnel - voir requirements-faces.txt"
            )

        backend = face_detect_backend()
        items = self._normalize_media(media_items, media_urls)
        if not items:
            return skip_result("aucune image a analyser")

        if backend in ("", "stub", "none", "off"):
            return skip_result(
                "backend non configure "
                "(FACE_DETECT_BACKEND=face_recognition|insightface)"
            )

        if backend == "insightface":
            try:
                import insightface  # noqa: F401
            except ImportError:
                return skip_result("insightface non installe (requirements-faces.txt)")
        elif backend in ("face_recognition", "dlib"):
            try:
                import face_recognition  # noqa: F401
            except ImportError:
                return skip_result(
                    "face_recognition non installe (requirements-faces.txt)"
                )
        else:
            return skip_result(f"backend inconnu: {backend}")

        try:
            from text_analysis.face_backends import run_backend_on_media

            faces, errors = run_backend_on_media(backend, items)
            now = datetime.now(timezone.utc).isoformat()
            for face in faces:
                face.setdefault("detected_at", now)
                face.setdefault("tool_name", "face_detect")

            if not faces and errors:
                return error_result("; ".join(errors[:3]))
            if not faces:
                return skip_result("aucun visage detecte")

            return ok_result(
                faces=faces,
                face_count=len(faces),
                backend=backend,
                images_scanned=min(
                    len(items),
                    int(os.getenv("FACE_DETECT_MAX_IMAGES", "5")),
                ),
                warnings=errors[:5] if errors else [],
            )
        except Exception as exc:
            return error_result(str(exc))

    @staticmethod
    def _normalize_media(
        media_items: Optional[List[Dict[str, Any]]],
        media_urls: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if isinstance(media_items, list):
            for m in media_items:
                if not isinstance(m, dict):
                    continue
                url = (m.get("url") or "").strip()
                if not url:
                    continue
                out.append(
                    {
                        "url": url,
                        "media_id": m.get("media_id") if isinstance(m.get("media_id"), int) else (
                            m.get("id") if isinstance(m.get("id"), int) else None
                        ),
                        "media_type": (m.get("media_type") or "image"),
                    }
                )
        if not out and media_urls:
            for u in media_urls:
                if u and str(u).strip():
                    out.append({"url": str(u).strip(), "media_type": "image"})
        return out


def detect_faces_on_urls(
    urls: List[str],
    *,
    article_id: Optional[int] = None,
    media_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """API directe pour Celery / services (hors runner texte)."""
    analyzer = FaceDetectAnalyzer()
    if not analyzer.is_available():
        return {"status": "skipped", "reason": "dependance non installee", "faces": []}
    block = analyzer.analyze("", media_urls=urls, media_items=media_items)
    faces = block.get("faces") if isinstance(block, dict) else []
    if not isinstance(faces, list):
        faces = []
    return {**block, "faces": faces, "article_id": article_id}
