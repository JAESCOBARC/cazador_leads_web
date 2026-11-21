# -*- coding: utf-8 -*-
"""
Contactos desde Instagram y Facebook.

Realidad técnica (comprobada): una petición automática a un perfil de Instagram devuelve solo una
cáscara de JavaScript, y Facebook devuelve apenas el nombre y un fragmento de la bio. El email, el
teléfono y el WhatsApp no vienen en el HTML sin iniciar sesión. Por eso hay dos vías honestas:

  1. leer_perfil():      lee la bio pública (og:description) del perfil que el propio negocio publicó en
                         su ficha de Maps. Gratis; devuelve algo solo cuando la bio incluye datos.
  2. buscar_perfiles():  busca el negocio en Google (SerpAPI, 1 crédito). Google muestra en sus fragmentos
                         la bio de Instagram/Facebook, y sirve también para negocios sin web.

Solo se leen perfiles públicos, sin iniciar sesión, sin recorrer seguidores ni publicaciones, y se
usa un User-Agent propio (no se suplanta a ningún rastreador). Todo dato extraído se muestra con su
fuente y debe verificarse a mano antes de enviar (CLAUDE.md).
"""

import html as html_lib
import json
import math
import os
import re
from urllib.parse import urlparse

import requests

import escaner

RE_RED = re.compile(r"^https?://([a-z0-9-]+\.)*(instagram|facebook)\.com/", re.I)
_META = (
    re.compile(r"<meta[^>]+(?:property|name)=[\"'](?:og:description|description)[\"'][^>]*content=[\"']([^\"']*)", re.I),
    re.compile(r"<meta[^>]+content=[\"']([^\"']*)[\"'][^>]*(?:property|name)=[\"'](?:og:description|description)[\"']", re.I),
)
_TELEFONO = re.compile(
    r"(?:(?:tel[eé]fono|tel|whatsapp|wsp|wapp|wa|cel(?:ular)?|llama(?:r|nos)?|citas|reservas|call)\W{0,6})"
    r"(\+?\d[\d\s().-]{7,17}\d)|(\+\d[\d\s().-]{7,17}\d)", re.I)
_GENERICAS = {"clinica", "clinicas", "veterinaria", "veterinario", "centro", "salon", "estudio", "grupo",
              "servicios", "consultorio", "taller", "tienda", "restaurante", "hotel", "academia", "instituto"}


class RedesError(Exception):
    pass


def es_perfil_red(url):
    return bool(url and RE_RED.match(url))


def extraer_de_texto(texto, fuente, via="perfil"):
    """Emails, WhatsApps y teléfonos que aparecen en un texto público (bio / fragmento de Google)."""
    t = html_lib.unescape(texto or "")
    emails, vistos = [], set()
    for m in escaner._EMAIL.finditer(t):
        e = escaner._email_valido(m.group(0))
        if e and e not in vistos:
            vistos.add(e)
            emails.append({"valor": e, "fuente": fuente, "via": via})
    was = []
    for m in escaner._WHATSAPP.finditer(t):
        n = m.group(1)
        if n not in {w["numero"] for w in was}:
            was.append({"numero": n, "link": f"https://wa.me/{n}", "fuente": fuente})
    tels = []
    for m in _TELEFONO.finditer(t):
        crudo = (m.group(1) or m.group(2)).strip()
        digitos = re.sub(r"\D", "", crudo)
        if not 9 <= len(digitos) <= 13:
            continue
        if re.fullmatch(r"(?:(?:19|20)\d{2}\D*)+", crudo):  # rachas de años, no teléfonos
            continue
        if digitos not in {x["digitos"] for x in tels}:
            tels.append({"numero": crudo, "digitos": digitos, "fuente": fuente})
    return {"emails": emails, "whatsapps": was, "telefonos": tels}


def descripcion_meta(html):
    for rx in _META:
        m = rx.search(html or "")
        if m:
            return html_lib.unescape(m.group(1)).strip()
    return ""


def leer_perfil(url):
    """Lee la bio pública del perfil que el negocio publicó en Maps. Nunca lanza."""
    if not es_perfil_red(url):
        return {"url": url, "estado": "no_aplica"}
    d = escaner.descargar(url, timeout=(4, 7))
    if d["estado"] != "ok":
        return {"url": url, "estado": d["estado"], "detalle": d.get("detalle")}
    desc = descripcion_meta(d.get("html", ""))
    contactos = extraer_de_texto(desc, url, via="bio pública")
    return {"url": url, "estado": "ok", "descripcion": desc[:300], "contactos": contactos}


# ------------------------------------------------------------------ búsqueda en Google (1 crédito)

def _tokens(nombre):
    n = escaner._norm(nombre)
    return [t for t in re.findall(r"[a-z0-9]{4,}", n) if t not in _GENERICAS]


def coincide(nombre, texto):
    """El texto menciona al menos la mitad de las palabras distintivas del nombre (evita homónimos)."""
    toks = _tokens(nombre)
    if not toks:
        return False
    t = escaner._norm(texto)
    return sum(1 for k in toks if k in t) >= math.ceil(len(toks) / 2)


def buscar_perfiles(nombre, ciudad, cache=None):
    """Busca Instagram/Facebook del negocio en Google. Devuelve perfiles y contactos publicados."""
    key = os.getenv("SERPAPI_KEY")
    if not key or key == "tu_api_key_aqui":
        raise RedesError("SERPAPI_KEY no configurada en .env")
    q = f'"{nombre}" {ciudad} (site:instagram.com OR site:facebook.com)'
    clave = f"gg|{q.lower()}"
    cacheado = cache.get(clave) if cache is not None else None
    creditos = 0
    if cacheado:
        data = json.loads(cacheado)
    else:
        try:
            r = requests.get("https://serpapi.com/search", timeout=30,
                             params={"engine": "google", "q": q, "num": 6, "hl": "es", "api_key": key})
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            raise RedesError(f"Error de conexión con SerpAPI: {e}") from e
        if "error" in data and "hasn't returned any results" not in str(data["error"]):
            raise RedesError(f"SerpAPI: {data['error']}")
        data = {"organic_results": data.get("organic_results") or []}
        creditos = 1
        if cache is not None:
            cache.set(clave, json.dumps(data, ensure_ascii=False))

    perfiles, emails, was, tels = [], [], [], []
    for res in data.get("organic_results", []):
        link = res.get("link") or ""
        if not es_perfil_red(link):
            continue
        texto = f"{res.get('title', '')} {res.get('snippet', '')}"
        if not coincide(nombre, texto):
            continue
        host = (urlparse(link).hostname or "").lower()
        perfiles.append({"url": link, "red": "instagram" if "instagram" in host else "facebook",
                         "titulo": (res.get("title") or "")[:140], "snippet": (res.get("snippet") or "")[:300]})
        c = extraer_de_texto(texto, link, via="bio pública (Google)")
        emails += [e for e in c["emails"] if e["valor"] not in {x["valor"] for x in emails}]
        was += [w for w in c["whatsapps"] if w["numero"] not in {x["numero"] for x in was}]
        tels += [t for t in c["telefonos"] if t["digitos"] not in {x["digitos"] for x in tels}]
    return {"perfiles": perfiles[:4], "emails": emails[:3], "whatsapps": was[:2], "telefonos": tels[:2],
            "creditos": creditos}
