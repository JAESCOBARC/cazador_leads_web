# -*- coding: utf-8 -*-
"""
Envío de correo de la aplicación (avisos). No usa IA.

Dos proveedores, elegidos por las variables de entorno (nunca se guardan credenciales en la base de datos):

  * API de Resend  (RESEND_API_KEY)  -> funciona en hostings que bloquean SMTP (p. ej. planes gratis de Render).
  * SMTP           (SMTP_HOST, SMTP_PUERTO, SMTP_USUARIO, SMTP_CLAVE) -> tu Gmail con "contraseña de aplicación",
                   Outlook, o el servidor de tu dominio.

Destinatarios: ALERTA_EMAIL_DESTINO (uno o varios, separados por coma). Remitente: EMAIL_REMITENTE.
Los errores que se muestran al usuario nunca incluyen contraseñas ni claves.
"""

import os
import re
import smtplib
import ssl
from email.message import EmailMessage

import requests

_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")


class CorreoError(Exception):
    pass


def _secretos():
    out = set()
    for k in ("SMTP_CLAVE", "RESEND_API_KEY"):
        v = os.getenv(k, "").strip()
        for variante in (v, v.replace(" ", "")):
            if len(variante) >= 6:
                out.add(variante)
    return out


def limpiar(texto):
    """Quita cualquier credencial que aparezca dentro de un mensaje de error."""
    t = str(texto)
    for s in sorted(_secretos(), key=len, reverse=True):
        t = t.replace(s, "***")
    return t


def destinatarios():
    crudos = re.split(r"[;,]", os.getenv("ALERTA_EMAIL_DESTINO", ""))
    return [c.strip() for c in crudos if _EMAIL.match(c.strip())][:5]


def proveedor():
    if os.getenv("RESEND_API_KEY", "").strip():
        return "resend"
    if os.getenv("SMTP_HOST", "").strip():
        return "smtp"
    return None


def remitente():
    r = os.getenv("EMAIL_REMITENTE", "").strip()
    if r:
        return r
    if proveedor() == "resend":
        return "Cazador Leads <onboarding@resend.dev>"
    return os.getenv("SMTP_USUARIO", "").strip() or "cazador-leads@localhost"


def enmascarar(email):
    local, _, dominio = email.partition("@")
    return (local[:1] + "***@" + dominio) if local else email


def configurado():
    return bool(proveedor() and destinatarios())


def _smtp(msg):
    host = os.getenv("SMTP_HOST", "").strip()
    try:
        puerto = int(os.getenv("SMTP_PUERTO", "587") or 587)
    except ValueError:
        puerto = 587
    seguridad = (os.getenv("SMTP_SEGURIDAD") or ("ssl" if puerto == 465 else "starttls")).strip().lower()
    ctx = ssl.create_default_context()
    try:
        conexion = smtplib.SMTP_SSL(host, puerto, timeout=15, context=ctx) if seguridad == "ssl" else smtplib.SMTP(host, puerto, timeout=15)
        with conexion as s:
            if seguridad == "starttls":
                s.starttls(context=ctx)
            usuario, clave = os.getenv("SMTP_USUARIO", "").strip(), os.getenv("SMTP_CLAVE", "").replace(" ", "")
            if usuario and clave:
                s.login(usuario, clave)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise CorreoError("El servidor de correo rechazó el usuario o la contraseña "
                          "(en Gmail hace falta una «contraseña de aplicación», no tu contraseña normal)") from e
    except (smtplib.SMTPException, OSError) as e:
        raise CorreoError(f"No se pudo enviar por SMTP: {limpiar(e)}") from e


def _resend(asunto, texto, html, destinos, reply_to=None):
    clave = os.getenv("RESEND_API_KEY", "").strip()
    try:
        r = requests.post("https://api.resend.com/emails", timeout=15, headers={"Authorization": f"Bearer {clave}"},
                          json={"from": remitente(), "to": destinos, "subject": asunto, "text": texto,
                                **({"html": html} if html else {}), **({"reply_to": reply_to} if reply_to else {})})
    except requests.RequestException as e:
        raise CorreoError(f"No se pudo contactar con Resend: {limpiar(e)}") from e
    if r.status_code >= 400:
        try:
            detalle = r.json().get("message") or ""
        except ValueError:
            detalle = ""
        raise CorreoError(f"Resend rechazó el envío ({r.status_code}): {limpiar(detalle) or 'sin detalle'}")


def enviar(asunto, texto, html=None, destinos=None, reply_to=None):
    """Envía un correo a los destinatarios configurados (o a `destinos`). Lanza CorreoError si no puede."""
    prov = proveedor()
    destinos = destinos or destinatarios()
    if not prov:
        raise CorreoError("No hay proveedor de correo configurado (define RESEND_API_KEY o SMTP_HOST)")
    if not destinos:
        raise CorreoError("No hay destinatarios válidos (define ALERTA_EMAIL_DESTINO)")
    asunto = re.sub(r"[\r\n]+", " ", asunto).strip()[:200]
    if prov == "resend":
        return _resend(asunto, texto, html, destinos, reply_to)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = asunto, remitente(), ", ".join(destinos)
    if reply_to and _EMAIL.match(reply_to):
        msg["Reply-To"] = reply_to
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype="html")
    return _smtp(msg)
