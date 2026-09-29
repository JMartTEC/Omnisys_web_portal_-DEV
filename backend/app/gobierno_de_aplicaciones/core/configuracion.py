"""
configuracion.py
----------------
Lee y escribe el .env desde la interfaz, para no tener que editarlo a mano.

REGLAS DE MANEJO DEL SECRETO. La API key es lo mas sensible del sistema y aqui
se trata como tal:

  1. NUNCA se devuelve al navegador. La pantalla solo recibe una version
     enmascarada ("sk-ant-api03-...QV4A"). Aunque el usuario la escribio, el
     servidor no se la regresa: si alguien abre la pantalla en ese equipo, no
     puede leer la llave que ya estaba guardada.
  2. NUNCA se escribe en los logs. Ni completa ni parcial.
  3. Si el campo llega vacio o enmascarado, se CONSERVA la que ya estaba. Asi
     el usuario puede cambiar el modelo o el workspace sin volver a teclear la
     llave, y sin que un guardado accidental la borre.
  4. Vive solo en el .env de esta carpeta, que esta en .gitignore.

El .env se reescribe conservando comentarios y el orden de las claves que ya
existian, para que siga siendo legible a mano.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

RUTA_ENV = Path(__file__).resolve().parents[3] / ".env"   # backend/.env

# Claves que administra la pantalla. El resto del .env no se toca.
CLAVES = [
    "AI_MODO",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_WORKSPACE_ID",
    "ANTHROPIC_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "OLLAMA_MODEL",
    "OLLAMA_HOST",
    "OLLAMA_MAX_CHARS",
]

SECRETAS = {"ANTHROPIC_API_KEY", "GEMINI_API_KEY"}

DEFECTOS = {
    "AI_MODO": "local",
    "ANTHROPIC_MODEL": "claude-sonnet-5",
    "GEMINI_MODEL": "gemini-2.5-flash",
    "OLLAMA_MODEL": "qwen3:8b",
    "OLLAMA_HOST": "http://127.0.0.1:11434",
    "OLLAMA_MAX_CHARS": "18000",
}

MODELOS_CLAUDE = [
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-haiku-4-5-20251001",
]

# Gemini SI lee imagenes (a diferencia de Ollama), asi que es un respaldo
# gratuito real cuando no hay llave de Claude -- no depende de que la
# maquina tenga algo corriendo localmente. flash-lite es la opcion mas
# ligera/rapida del nivel gratuito; flash es el equilibrio recomendado.
MODELOS_GEMINI = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
]

MODOS = [
    {"valor": "local", "etiqueta": "Local (Ollama) · sin API key, solo desarrollo"},
    {"valor": "claude", "etiqueta": "Claude API · requiere llave"},
    {"valor": "gemini", "etiqueta": "Gemini API · requiere llave gratuita"},
    {"valor": "", "etiqueta": "Automatico (Claude, si no Gemini, si no local)"},
]


# ---------------------------------------------------------------------------
# Lectura y escritura del .env
# ---------------------------------------------------------------------------

def leer_env() -> dict[str, str]:
    """Valores crudos del archivo. Uso interno; no exponer tal cual."""
    valores: dict[str, str] = {}
    if not RUTA_ENV.exists():
        return valores
    for linea in RUTA_ENV.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip()
    return valores


def enmascarar(valor: str) -> str:
    """sk-ant-api03-xxxxx...QV4A — reconocible sin ser utilizable."""
    if not valor:
        return ""
    if len(valor) <= 12:
        return "•" * len(valor)
    return f"{valor[:12]}…{valor[-4:]}"


def estado() -> dict:
    """Lo que ve la pantalla. La llave va ENMASCARADA, nunca completa."""
    env = leer_env()
    llave = env.get("ANTHROPIC_API_KEY", "")
    llave_gemini = env.get("GEMINI_API_KEY", "")
    return {
        "ai_modo": env.get("AI_MODO", DEFECTOS["AI_MODO"]),
        "anthropic_model": env.get("ANTHROPIC_MODEL", DEFECTOS["ANTHROPIC_MODEL"]),
        "anthropic_workspace_id": env.get("ANTHROPIC_WORKSPACE_ID", ""),
        "gemini_model": env.get("GEMINI_MODEL", DEFECTOS["GEMINI_MODEL"]),
        "ollama_model": env.get("OLLAMA_MODEL", DEFECTOS["OLLAMA_MODEL"]),
        "ollama_host": env.get("OLLAMA_HOST", DEFECTOS["OLLAMA_HOST"]),
        "ollama_max_chars": env.get("OLLAMA_MAX_CHARS", DEFECTOS["OLLAMA_MAX_CHARS"]),
        # --- sobre las llaves, solo metadatos ---
        "tiene_llave": bool(llave),
        "llave_enmascarada": enmascarar(llave),
        "tiene_llave_gemini": bool(llave_gemini),
        "llave_gemini_enmascarada": enmascarar(llave_gemini),
        # --- catalogos para la pantalla ---
        "modos": MODOS,
        "modelos_claude": MODELOS_CLAUDE,
        "modelos_gemini": MODELOS_GEMINI,
        "ruta_env": str(RUTA_ENV),
    }


def _es_enmascarada(valor: str) -> bool:
    """El navegador devuelve la mascara si el usuario no la toco."""
    return "…" in valor or "•" in valor


def guardar(entrada: dict) -> dict:
    """Escribe el .env y actualiza el proceso en caliente.

    Devuelve {"cambios": [...]} SIN incluir valores secretos.
    """
    actual = leer_env()
    nuevo = dict(actual)
    cambios: list[str] = []

    for clave in CLAVES:
        if clave.lower() not in entrada:
            continue
        valor = str(entrada[clave.lower()] or "").strip()

        if clave in SECRETAS:
            # Vacia o enmascarada => conservar la que ya estaba.
            if not valor or _es_enmascarada(valor):
                continue
            if actual.get(clave) != valor:
                cambios.append(f"{clave} actualizada")
        else:
            if actual.get(clave, "") != valor:
                cambios.append(f"{clave} = {valor or '(vacio)'}")

        nuevo[clave] = valor

    # --- reescribir conservando comentarios y orden ---
    lineas_salida: list[str] = []
    vistas: set[str] = set()
    if RUTA_ENV.exists():
        for linea in RUTA_ENV.read_text(encoding="utf-8").splitlines():
            crudo = linea.strip()
            if not crudo or crudo.startswith("#") or "=" not in crudo:
                lineas_salida.append(linea)
                continue
            clave = crudo.split("=", 1)[0].strip()
            if clave in nuevo:
                lineas_salida.append(f"{clave}={nuevo[clave]}")
                vistas.add(clave)
            else:
                lineas_salida.append(linea)
    for clave, valor in nuevo.items():
        if clave not in vistas:
            lineas_salida.append(f"{clave}={valor}")

    RUTA_ENV.write_text("\n".join(lineas_salida).rstrip() + "\n", encoding="utf-8")

    # El proceso ya esta corriendo: se actualiza el entorno en vivo para que
    # el cambio aplique sin reiniciar el servidor.
    for clave, valor in nuevo.items():
        os.environ[clave] = valor

    return {"cambios": cambios}


def borrar_llave(clave: str = "ANTHROPIC_API_KEY") -> None:
    """Quita una API key del .env y del proceso. Para cuando hay que rotarla.

    `clave` es "ANTHROPIC_API_KEY" (por defecto, compatibilidad con el
    llamado anterior) o "GEMINI_API_KEY".
    """
    if clave not in SECRETAS:
        raise ValueError(f"clave no reconocida: {clave}")
    if RUTA_ENV.exists():
        lineas = [l for l in RUTA_ENV.read_text(encoding="utf-8").splitlines()
                  if not l.strip().startswith(f"{clave}=")]
        lineas.append(f"{clave}=")
        RUTA_ENV.write_text("\n".join(lineas).rstrip() + "\n", encoding="utf-8")
    os.environ[clave] = ""
