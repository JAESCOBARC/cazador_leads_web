# -*- coding: utf-8 -*-
"""
Ajustes gestionados desde la propia app (sección «Ajustes», solo administradores).

Sustituye la necesidad de poner en Render la clave de SerpAPI, las credenciales del correo o la firma:

  * Prioridad: valor guardado en la app  >  variable de entorno  >  valor por defecto.
    Así nada se rompe si todavía tienes las variables en Render.
  * Las CLAVES (SerpAPI, contraseña SMTP, API de Resend) se guardan CIFRADAS (Fernet/AES) con una clave derivada
    de SECRET_KEY. Nunca se devuelven al navegador: la interfaz solo sabe si están configuradas y de dónde vienen.
  * Sin una SECRET_KEY estable no se permite guardar claves (no se podrían descifrar tras un reinicio).
  * Todo cambio queda con su autor y fecha (nunca con el valor).
"""

import base64
import hashlib
import ipaddress
import os
import re
import socket
import threading
import time

from sqlalchemy import delete, insert, select

import db

try:
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover - sin la librería no se pueden guardar claves
    Fernet = None

TTL = 30  # segundos: cuánto vive la caché de lo guardado en la base de datos
_cache = {"t": 0.0, "d": None}
_lock = threading.Lock()


class AjusteError(Exception):
    pass


GRUPOS = [
    ("serpapi", "Motor de búsqueda (SerpAPI)",
     "Con esta clave la app consulta Google Maps y Google. La encuentras en serpapi.com → Manage API key."),
    ("correo", "Correo",
     "Se usa para los avisos de cuota y para enviar propuestas a clientes (siempre manualmente, lead a lead). "
     "Elige una opción: tu Gmail por SMTP o la API de Resend."),
    ("remitente", "Remitente y firma",
     "Datos que aparecen en los mensajes. Mientras falte alguno, la app no deja enviar correos."),
]

CAMPOS = [
    dict(clave="SERPAPI_KEY", grupo="serpapi", tipo="secreto", etiqueta="Clave API de SerpAPI"),
    dict(clave="SERPAPI_CUOTA_MES", grupo="serpapi", tipo="numero", etiqueta="Búsquedas de tu plan al mes", defecto="100", min=1, max=1000000,
         ayuda="El plan gratis incluye 100. Es la referencia del medidor mensual y de los avisos."),
    dict(clave="ALERTA_EMAIL_DESTINO", grupo="correo", sub="Avisos de cuota", tipo="emails", etiqueta="Email que recibe los avisos",
         ayuda="Uno o varios, separados por coma."),
    dict(clave="ALERTA_UMBRALES", grupo="correo", sub="Avisos de cuota", tipo="enteros", etiqueta="Avisar al llegar al (%)", defecto="80",
         ayuda="Por ejemplo 80, o 80, 100. Se avisa una vez por mes y por umbral."),
    dict(clave="SMTP_HOST", grupo="correo", sub="Opción A · Gmail / SMTP", tipo="host", etiqueta="Servidor SMTP", placeholder="smtp.gmail.com",
         ayuda="En Gmail: smtp.gmail.com. Ojo: el plan gratis de Render bloquea SMTP; allí usa la opción B."),
    dict(clave="SMTP_PUERTO", grupo="correo", sub="Opción A · Gmail / SMTP", tipo="numero", etiqueta="Puerto", defecto="587", min=1, max=65535),
    dict(clave="SMTP_USUARIO", grupo="correo", sub="Opción A · Gmail / SMTP", tipo="texto", etiqueta="Usuario (tu correo)", placeholder="tu_correo@gmail.com"),
    dict(clave="SMTP_CLAVE", grupo="correo", sub="Opción A · Gmail / SMTP", tipo="secreto", etiqueta="Contraseña de aplicación",
         ayuda="No es tu contraseña normal: créala en myaccount.google.com/apppasswords (requiere verificación en dos pasos)."),
    dict(clave="RESEND_API_KEY", grupo="correo", sub="Opción B · Resend (API)", tipo="secreto", etiqueta="API key de Resend",
         ayuda="Funciona en Render gratis. Para escribir a clientes necesitas verificar un dominio tuyo en Resend. Tiene prioridad sobre SMTP."),
    dict(clave="EMAIL_REMITENTE", grupo="correo", sub="Envío de propuestas", tipo="remitente", etiqueta="Remitente que ve el cliente",
         placeholder="Tu Nombre <hola@tudominio.com>", ayuda="Si lo dejas vacío se usa tu usuario SMTP."),
    dict(clave="EMAIL_RESPONDER_A", grupo="correo", sub="Envío de propuestas", tipo="email", etiqueta="Las respuestas llegan a (opcional)"),
    dict(clave="ENVIO_MAX_DIA", grupo="correo", sub="Envío de propuestas", tipo="numero", etiqueta="Máximo de propuestas por día", defecto="5", min=1, max=100,
         ayuda="Un tope bajo protege la reputación de tu cuenta de correo."),
    dict(clave="REMITENTE_NOMBRE", grupo="remitente", tipo="texto", etiqueta="Tu nombre"),
    dict(clave="REMITENTE_CARGO", grupo="remitente", tipo="texto", etiqueta="Tu cargo", placeholder="Desarrollador web"),
    dict(clave="AGENCIA_NOMBRE", grupo="remitente", tipo="texto", etiqueta="Nombre de tu agencia"),
    dict(clave="REMITENTE_CONTACTO", grupo="remitente", tipo="texto", etiqueta="Email o teléfono de contacto"),
    dict(clave="CASO_EXITO", grupo="remitente", tipo="largo", etiqueta="Caso de éxito real (opcional)",
         ayuda="Una frase con un resultado verdadero, p. ej. «una clínica de Cali pasó de 4 a 15 citas por semana». Si lo dejas vacío no se inventa ninguno."),
]
_IDX = {c["clave"]: c for c in CAMPOS}

_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")
_REMITENTE = re.compile(r"^[^<>\r\n]{1,100}<[^<>@\s]+@[^<>@\s]+\.[A-Za-z]{2,}>$")
_HOST = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


# ------------------------------------------------------------------ cifrado
def _fernet():
    base = os.environ.get("SECRET_KEY", "").strip()
    if Fernet is None or len(base) < 16:
        return None
    clave = base64.urlsafe_b64encode(hashlib.sha256(("cazador-ajustes-v1|" + base).encode("utf-8")).digest())
    return Fernet(clave)


def cifrado_disponible():
    return _fernet() is not None


# ------------------------------------------------------------------ lectura (con caché corta)
def _leer_db():
    try:
        with db.engine.connect() as conn:
            filas = conn.execute(select(db.ajustes)).mappings().all()
    except Exception:  # noqa: BLE001 - p. ej. la tabla aún no existe (modo consola): se usa solo el entorno
        return {}
    f, out = _fernet(), {}
    for r in filas:
        valor, ilegible = r["valor"], False
        if r["secreto"]:
            try:
                valor = f.decrypt(valor.encode("utf-8")).decode("utf-8") if f else None
                ilegible = f is None
            except Exception:  # noqa: BLE001 - cambió la SECRET_KEY o el dato está dañado
                valor, ilegible = None, True
        out[r["clave"]] = {"valor": valor, "ilegible": ilegible, "en": r["actualizado_en"], "por": r["actualizado_por"]}
    return out


def _datos():
    with _lock:
        if _cache["d"] is None or time.time() - _cache["t"] > TTL:
            _cache.update(d=_leer_db(), t=time.time())
        return _cache["d"]


def invalidar():
    with _lock:
        _cache.update(d=None, t=0.0)


def obtener(clave, defecto=""):
    """Valor efectivo: guardado en la app > variable de entorno > defecto."""
    r = _datos().get(clave)
    if r and r["valor"]:
        return r["valor"]
    return os.getenv(clave) or defecto


def obtener_entero(clave, defecto=None):
    try:
        return int(str(obtener(clave)).strip())
    except ValueError:
        return defecto


def origen(clave):
    r = _datos().get(clave)
    if r and r["valor"]:
        return "app"
    return "entorno" if (os.getenv(clave) or "").strip() else None


def secretos():
    """Todas las claves en uso (de la app y del entorno): sirven para borrarlas de cualquier mensaje de error."""
    out = set()
    for c in CAMPOS:
        if c["tipo"] != "secreto":
            continue
        for v in (obtener(c["clave"]), os.getenv(c["clave"], "")):
            v = (v or "").strip()
            for variante in (v, v.replace(" ", "")):
                if len(variante) >= 6:
                    out.add(variante)
    return out


def limpiar(texto):
    t = str(texto)
    for s in sorted(secretos(), key=len, reverse=True):
        t = t.replace(s, "***")
    return t


# ------------------------------------------------------------------ validación
def _host_publico(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError) as e:
        raise AjusteError("No se pudo resolver el servidor SMTP: revisa el nombre") from e
    for i in infos:
        ip = ipaddress.ip_address(i[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise AjusteError("El servidor SMTP apunta a una dirección interna: no está permitido")


def validar(campo, valor):
    """Devuelve el valor normalizado ('' = sin valor) o lanza AjusteError."""
    et, tipo = campo["etiqueta"], campo["tipo"]
    v = str(valor if valor is not None else "").strip()
    if v == "":
        return ""
    if _CONTROL.search(v):
        raise AjusteError(f"«{et}» no puede tener saltos de línea ni caracteres de control")
    limite = 300 if tipo == "largo" else 200
    if len(v) > limite:
        raise AjusteError(f"«{et}» es demasiado largo (máximo {limite} caracteres)")
    if tipo == "secreto" and len(v) < 6:
        raise AjusteError(f"«{et}» parece demasiado corta")
    if tipo == "numero":
        try:
            n = int(v)
        except ValueError as e:
            raise AjusteError(f"«{et}» debe ser un número entero") from e
        if not campo["min"] <= n <= campo["max"]:
            raise AjusteError(f"«{et}» debe estar entre {campo['min']} y {campo['max']}")
        return str(n)
    if tipo == "email":
        if not _EMAIL.match(v):
            raise AjusteError(f"«{et}» no es un email válido")
    if tipo == "emails":
        items = [x.strip() for x in re.split(r"[;,]", v) if x.strip()]
        if not items or len(items) > 5 or not all(_EMAIL.match(x) for x in items):
            raise AjusteError(f"«{et}»: escribe de 1 a 5 emails válidos separados por coma")
        return ", ".join(items)
    if tipo == "enteros":
        try:
            nums = sorted({int(x) for x in re.split(r"[;,\s]+", v) if x})
        except ValueError as e:
            raise AjusteError(f"«{et}»: escribe porcentajes enteros separados por coma") from e
        if not nums or len(nums) > 6 or not all(1 <= n <= 200 for n in nums):
            raise AjusteError(f"«{et}»: de 1 a 6 porcentajes entre 1 y 200")
        return ", ".join(map(str, nums))
    if tipo == "host":
        if not _HOST.match(v):
            raise AjusteError(f"«{et}» no es un nombre de servidor válido")
        _host_publico(v)
    if tipo == "remitente":
        if not (_EMAIL.match(v) or _REMITENTE.match(v)):
            raise AjusteError(f"«{et}»: usa un email o el formato Nombre <email@dominio.com>")
    return v


# ------------------------------------------------------------------ escritura
def guardar(cambios, borrar=(), importar=(), usuario_id=None):
    """Valida todo primero y escribe de forma atómica. Devuelve las claves tocadas.
    - cambios: {clave: valor}. En una clave secreta un valor vacío significa «no cambiar»; en las demás, «volver al entorno».
    - borrar: claves cuyo valor guardado se elimina (se vuelve a la variable de entorno, si existe).
    - importar: claves secretas cuyo valor del entorno (Render) se copia a la app, sin que pase por el navegador."""
    for k in [*cambios, *borrar, *importar]:
        if k not in _IDX:
            raise AjusteError(f"Ajuste desconocido: {k}")
    escribir, eliminar = {}, set(borrar)
    for k, v in cambios.items():
        c = _IDX[k]
        if c["tipo"] == "secreto":
            if v in (None, ""):
                continue
            escribir[k] = validar(c, v)
        else:
            nuevo = validar(c, v)
            if nuevo == "":
                eliminar.add(k)
            else:
                escribir[k] = nuevo
    for k in importar:
        c = _IDX[k]
        if c["tipo"] != "secreto":
            raise AjusteError(f"«{c['etiqueta']}» no es una clave: no se importa")
        del_entorno = (os.getenv(k) or "").strip()
        if not del_entorno:
            raise AjusteError(f"No hay valor de «{c['etiqueta']}» en las variables de entorno")
        escribir[k] = validar(c, del_entorno)
    f = _fernet()
    if any(_IDX[k]["tipo"] == "secreto" for k in escribir) and f is None:
        raise AjusteError("Para guardar claves hace falta una SECRET_KEY estable (mínimo 16 caracteres) en el entorno: "
                          "se usa para cifrarlas. En Render se genera sola con render.yaml.")
    with db.engine.begin() as conn:
        for k in set(escribir) | eliminar:
            conn.execute(delete(db.ajustes).where(db.ajustes.c.clave == k))
        for k, v in escribir.items():
            secreto = _IDX[k]["tipo"] == "secreto"
            conn.execute(insert(db.ajustes).values(
                clave=k, valor=f.encrypt(v.encode("utf-8")).decode("utf-8") if secreto else v, secreto=secreto,
                actualizado_en=db.ahora(), actualizado_por=usuario_id))
    invalidar()
    return sorted(set(escribir) | eliminar)


# ------------------------------------------------------------------ estado para la interfaz (sin secretos)
def estado():
    datos = _datos()
    with db.engine.connect() as conn:
        nombres = {u.id: u.nombre for u in conn.execute(select(db.usuarios.c.id, db.usuarios.c.nombre))}
    grupos = []
    for gid, titulo, ayuda in GRUPOS:
        campos = []
        for c in (x for x in CAMPOS if x["grupo"] == gid):
            r = datos.get(c["clave"])
            en_app = bool(r and r["valor"])
            env = (os.getenv(c["clave"]) or "").strip()
            item = {"clave": c["clave"], "etiqueta": c["etiqueta"], "tipo": c["tipo"], "sub": c.get("sub"), "ayuda": c.get("ayuda", ""),
                    "placeholder": c.get("placeholder", ""), "defecto": c.get("defecto", ""),
                    "origen": "app" if en_app else ("entorno" if env else None), "ilegible": bool(r and r["ilegible"]),
                    "actualizado_en": r["en"].isoformat() if r and r["en"] else None,
                    "actualizado_por": nombres.get(r["por"]) if r else None}
            if c["tipo"] != "secreto":      # los secretos NUNCA salen del servidor
                item["valor"] = r["valor"] if en_app else env
            campos.append(item)
        grupos.append({"id": gid, "titulo": titulo, "ayuda": ayuda, "campos": campos})
    return {"grupos": grupos, "cifrado_disponible": cifrado_disponible()}
