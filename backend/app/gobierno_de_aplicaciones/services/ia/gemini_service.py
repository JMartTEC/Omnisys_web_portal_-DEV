"""
gemini_service.py
------------------
Proveedor de respaldo GRATUITO de clasificacion, via la API de Google Gemini.

A diferencia de Ollama, no corre nada en la maquina: solo necesita una API
key gratuita de Google AI Studio (aistudio.google.com/apikey, sin tarjeta de
credito). Por eso es el respaldo preferido cuando no hay ANTHROPIC_API_KEY:
no depende de que el equipo tenga un servidor local corriendo.

El contrato es identico al de claude_service.clasificar: mismas entradas,
mismo JSON de salida, misma taxonomia. A diferencia de Ollama, Gemini SI
puede ver imagenes, asi que los diagramas se siguen analizando igual que con
la API de Claude (no hay que descartar "diagramas" como en modo local).
"""

from __future__ import annotations

import base64
import logging
import os

from . import claude_service

log = logging.getLogger(__name__)


def _api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or "").strip()


def _modelo() -> str:
    return (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()


def _max_tokens() -> int:
    try:
        return int(os.getenv("GEMINI_MAX_TOKENS") or 16000)
    except ValueError:
        return 16000


def _cliente():
    from google import genai
    return genai.Client(api_key=_api_key())


def _traducir_error(exc: Exception) -> str:
    texto = str(exc)
    baja = texto.lower()
    if "api key not valid" in baja or "api_key_invalid" in baja or "401" in texto or "permission_denied" in baja:
        return ("La API rechazo la llave. Consigue una nueva gratis en "
                "aistudio.google.com/apikey y vuelve a guardarla.")
    if "quota" in baja or "429" in texto or "rate" in baja or "resource_exhausted" in baja:
        return ("Se alcanzo el limite gratuito de Gemini por ahora. Espera un "
                "momento y prueba de nuevo, o usa otro proveedor mientras tanto.")
    return texto[:300]


def disponible() -> tuple[bool, str]:
    """Comprueba que la llave sea valida, SIN gastar cuota de generacion
    (a diferencia de una clasificacion real, solo lista modelos)."""
    if not _api_key():
        return False, "No hay API key de Gemini guardada."
    try:
        cliente = _cliente()
        next(iter(cliente.models.list()), None)
        return True, ""
    except Exception as exc:
        return False, _traducir_error(exc)


def _contenido_usuario(texto_doc: str, candidatos: dict, imagenes: list[dict]) -> list:
    from google.genai import types

    partes: list = []
    for img in imagenes:
        partes.append(types.Part.from_bytes(
            data=base64.b64decode(img["base64"]),
            mime_type=img["media_type"],
        ))
    partes.append(
        f"{claude_service._bloque_candidatos(candidatos)}\n\n"
        f"=== DOCUMENTO A CLASIFICAR ===\n\n{texto_doc}\n\n"
        f"=== FIN DEL DOCUMENTO ===\n\n"
        f"Devuelve unicamente el JSON del esquema."
    )
    return partes


def clasificar(texto_doc: str, candidatos: dict, imagenes: list[dict]) -> dict:
    if not _api_key():
        raise RuntimeError(
            "Falta GEMINI_API_KEY. Consiguela gratis en aistudio.google.com/apikey "
            "y pegala en Configuracion."
        )

    from google.genai import types

    modelo = _modelo()
    cliente = _cliente()

    try:
        respuesta = cliente.models.generate_content(
            model=modelo,
            contents=_contenido_usuario(texto_doc, candidatos, imagenes),
            config=types.GenerateContentConfig(
                system_instruction=claude_service.construir_system_prompt(),
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=_max_tokens(),
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini no respondio correctamente: {_traducir_error(exc)}") from None

    texto_respuesta = (getattr(respuesta, "text", None) or "").strip()
    if not texto_respuesta:
        raise RuntimeError(
            "Gemini devolvio una respuesta vacia (puede que el documento haya "
            "activado un filtro de seguridad). Revisa el log para mas detalle."
        )

    datos = claude_service._extraer_json(texto_respuesta)

    uso_meta = getattr(respuesta, "usage_metadata", None)
    datos["_uso"] = {
        "proveedor": "gemini",
        "modelo": modelo,
        "tokens_entrada": getattr(uso_meta, "prompt_token_count", 0) if uso_meta else 0,
        "tokens_salida": getattr(uso_meta, "candidates_token_count", 0) if uso_meta else 0,
    }

    log.info("gemini respondio | modelo=%s tokens_entrada=%s tokens_salida=%s",
              modelo, datos["_uso"]["tokens_entrada"], datos["_uso"]["tokens_salida"])

    return datos
