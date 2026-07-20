"""Detection de visages (stub pluggable).

Pas de dependance lourde requise : status skipped si aucune lib.
Brancher InsightFace / face_recognition plus tard via FACE_DETECT_BACKEND.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from text_analysis.base import error_result, ok_result, skip_result


class FaceDetectAnalyzer:
    """Analyseur enregistre dans le runner (tool_name=face_detect).

    Note: TextAnalyzer.analyze(text) est le contrat commun ; pour les visages
    on lit les URLs image depuis le contexte optionnel `media_urls`.
    """

    name = "face_detect"

    def is_available(self) -> bool:
        backend = (os.getenv("FACE_DETECT_BACKEND") or "stub").strip().lower()
        if backend in ("", "stub", "none", "off"):
            return True  # stub toujours "dispo" mais renvoie skipped
        if backend in ("insightface",):
            try:
                import insightface  # noqa: F401
                return True
            except ImportError:
                return False
        if backend in ("face_recognition", "dlib"):
            try:
                import face_recognition  # noqa: F401
                return True
            except ImportError:
                return False
        return True

    def analyze(
        self,
        text: str,
        *,
        lang_hint: Optional[str] = None,
        media_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        backend = (os.getenv("FACE_DETECT_BACKEND") or "stub").strip().lower()
        urls = [u for u in (media_urls or []) if u]
        if not urls:
            return skip_result("aucune image a analyser")

        if backend in ("", "stub", "none", "off"):
            return skip_result(
                "backend visage non configure (FACE_DETECT_BACKEND=insightface|face_recognition)"
            )

        try:
            if backend == "insightface":
                return self._analyze_insightface(urls)
            if backend in ("face_recognition", "dlib"):
                return self._analyze_face_recognition(urls)
            return skip_result(f"backend inconnu: {backend}")
        except Exception as exc:
            return error_result(str(exc))

    def _analyze_insightface(self, urls: List[str]) -> Dict[str, Any]:
        # Placeholder : lib presente mais download images non branche ici
        return skip_result(
            "insightface installe ; telecharger/analyser les images non implemente encore"
        )

    def _analyze_face_recognition(self, urls: List[str]) -> Dict[str, Any]:
        return skip_result(
            "face_recognition installe ; telecharger/analyser les images non implemente encore"
        )


def detect_faces_on_urls(
    urls: List[str],
    *,
    article_id: Optional[int] = None,
) -> Dict[str, Any]:
    """API directe pour Celery / services (hors runner texte)."""
    analyzer = FaceDetectAnalyzer()
    if not analyzer.is_available():
        return {"status": "skipped", "reason": "dependance non installee", "faces": []}
    block = analyzer.analyze("", media_urls=urls)
    faces = block.get("faces") if isinstance(block, dict) else []
    if not isinstance(faces, list):
        faces = []
    return {**block, "faces": faces, "article_id": article_id}
