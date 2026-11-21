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

import base64
import html as _html
import os
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage

import requests

import ajustes

_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")


class CorreoError(Exception):
    pass


def limpiar(texto):
    """Quita cualquier credencial (de la app o del entorno) que aparezca dentro de un mensaje de error."""
    return ajustes.limpiar(texto)


def destinatarios():
    crudos = re.split(r"[;,]", ajustes.obtener("ALERTA_EMAIL_DESTINO"))
    return [c.strip() for c in crudos if _EMAIL.match(c.strip())][:5]


def proveedor():
    if ajustes.obtener("RESEND_API_KEY").strip():
        return "resend"
    if ajustes.obtener("SMTP_HOST").strip():
        return "smtp"
    return None


def remitente():
    r = ajustes.obtener("EMAIL_REMITENTE").strip()
    if r:
        return r
    if proveedor() == "resend":
        return "Cazador Leads <onboarding@resend.dev>"
    return ajustes.obtener("SMTP_USUARIO").strip() or "cazador-leads@localhost"


def enmascarar(email):
    local, _, dominio = email.partition("@")
    return (local[:1] + "***@" + dominio) if local else email


def configurado():
    return bool(proveedor() and destinatarios())


def _conectar_ipv4(self, host, puerto, timeout):
    """Conecta solo por IPv4: muchos hostings (Render) no tienen salida IPv6 y falla con «Network is unreachable»."""
    ultimo = None
    for fam, tipo, proto, _, dir_ in socket.getaddrinfo(host, puerto, socket.AF_INET, socket.SOCK_STREAM):
        try:
            return socket.create_connection(dir_[:2], timeout)
        except OSError as e:
            ultimo = e
    raise ultimo or OSError(f"No se pudo resolver {host} por IPv4")


class _SMTP4(smtplib.SMTP):
    def _get_socket(self, host, puerto, timeout):
        return _conectar_ipv4(self, host, puerto, timeout)


class _SMTPSSL4(smtplib.SMTP_SSL):
    def _get_socket(self, host, puerto, timeout):
        s = _conectar_ipv4(self, host, puerto, timeout)
        return self.context.wrap_socket(s, server_hostname=self._host)


def _smtp(msg):
    host = ajustes.obtener("SMTP_HOST").strip()
    try:
        puerto = int(ajustes.obtener("SMTP_PUERTO", "587") or 587)
    except ValueError:
        puerto = 587
    seguridad = (os.getenv("SMTP_SEGURIDAD") or ("ssl" if puerto == 465 else "starttls")).strip().lower()
    ctx = ssl.create_default_context()
    try:
        conexion = _SMTPSSL4(host, puerto, timeout=15, context=ctx) if seguridad == "ssl" else _SMTP4(host, puerto, timeout=15)
        with conexion as s:
            if seguridad == "starttls":
                s.starttls(context=ctx)
            usuario, clave = ajustes.obtener("SMTP_USUARIO").strip(), ajustes.obtener("SMTP_CLAVE").replace(" ", "")
            if usuario and clave:
                s.login(usuario, clave)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise CorreoError("El servidor de correo rechazó el usuario o la contraseña "
                          "(en Gmail hace falta una «contraseña de aplicación», no tu contraseña normal)") from e
    except (smtplib.SMTPException, OSError) as e:
        extra = ""
        if isinstance(e, OSError) and not isinstance(e, smtplib.SMTPException):
            extra = (" Tu servidor no puede conectar con el correo: si la app está en Render gratis, bloquea los puertos SMTP "
                     "(25, 465, 587). Usa Resend (API) en Ajustes → Correo, o un plan de pago de Render.")
        raise CorreoError(f"No se pudo enviar por SMTP: {limpiar(e)}.{extra}") from e


def _resend(asunto, texto, html, destinos, reply_to=None, imagenes=None):
    clave = ajustes.obtener("RESEND_API_KEY").strip()
    adjuntos = [{"filename": i["nombre"], "content": base64.b64encode(i["datos"]).decode("ascii"), "content_id": i["cid"]}
                for i in (imagenes or [])]
    try:
        r = requests.post("https://api.resend.com/emails", timeout=15, headers={"Authorization": f"Bearer {clave}"},
                          json={"from": remitente(), "to": destinos, "subject": asunto, "text": texto,
                                **({"html": html} if html else {}), **({"reply_to": reply_to} if reply_to else {}),
                                **({"attachments": adjuntos} if adjuntos else {})})
    except requests.RequestException as e:
        raise CorreoError(f"No se pudo contactar con Resend: {limpiar(e)}") from e
    if r.status_code >= 400:
        try:
            detalle = r.json().get("message") or ""
        except ValueError:
            detalle = ""
        raise CorreoError(f"Resend rechazó el envío ({r.status_code}): {limpiar(detalle) or 'sin detalle'}")


def html_propuesta(cuerpo, baja, imagen=None, aviso=None, enlaces=None):
    """HTML sencillo de una propuesta: el texto tal cual (escapado), la imagen de firma incrustada (cid:) y la línea de baja.
    Todo lo que viene del usuario o del negocio se escapa: nunca se interpreta como HTML.
    enlaces: URLs https del propio remitente (agenda, WhatsApp) que se vuelven clicables; ninguna otra URL lo hace."""
    esc = lambda t: _html.escape(t, quote=True)  # noqa: E731

    def parrafo(p):
        t = esc(p)
        for u in sorted({u for u in (enlaces or []) if u.startswith("https://")}, key=len, reverse=True):
            e = esc(u)
            t = t.replace(e, f'<a href="{e}" style="color:#1769aa">{e}</a>')
        return t.replace(chr(10), "<br>")

    parrafos = "".join(f'<p style="margin:0 0 14px">{parrafo(p)}</p>' for p in cuerpo.split("\n\n") if p.strip())
    img = ""
    if imagen:
        img = (f'<p style="margin:18px 0 0"><img src="cid:{imagen["cid"]}" width="{int(imagen["ancho"])}" alt="{esc(imagen.get("alt") or "Firma")}" '
               f'style="display:block;border:0;max-width:100%;height:auto"></p>')
    cab = f'<p style="margin:0 0 18px;padding:8px 10px;background:#fff4d6;color:#6b4e00;font-size:13px">{esc(aviso)}</p>' if aviso else ""
    return ('<!doctype html><html><body style="margin:0;padding:16px;background:#ffffff">'
            '<div style="max-width:600px;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#1d2733">'
            f'{cab}{parrafos}{img}'
            f'<p style="margin:22px 0 0;font-size:12px;color:#6b7785">{esc(baja)}</p></div></body></html>')


def enviar(asunto, texto, html=None, destinos=None, reply_to=None, imagenes=None):
    """Envía un correo a los destinatarios configurados (o a `destinos`). Lanza CorreoError si no puede.
    imagenes: lista de {cid, datos (bytes), tipo ('image/png'…), nombre} incrustadas en el html con <img src="cid:...">."""
    prov = proveedor()
    destinos = destinos or destinatarios()
    if not prov:
        raise CorreoError("No hay proveedor de correo configurado (define RESEND_API_KEY o SMTP_HOST)")
    if not destinos:
        raise CorreoError("No hay destinatarios válidos (define ALERTA_EMAIL_DESTINO)")
    asunto = re.sub(r"[\r\n]+", " ", asunto).strip()[:200]
    if prov == "resend":
        return _resend(asunto, texto, html, destinos, reply_to, imagenes)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = asunto, remitente(), ", ".join(destinos)
    if reply_to and _EMAIL.match(reply_to):
        msg["Reply-To"] = reply_to
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype="html")
        for i in (imagenes or []):
            tipo, _, subtipo = i["tipo"].partition("/")
            msg.get_payload()[-1].add_related(i["datos"], maintype=tipo, subtype=subtipo, cid=f"<{i['cid']}>", filename=i["nombre"])
    return _smtp(msg)
