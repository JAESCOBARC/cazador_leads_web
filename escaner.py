# -*- coding: utf-8 -*-
"""
Escáner de oportunidades.

Para cada negocio encontrado en Google Maps decide QUÉ LE FALTA y cuánto vale la pena
escribirle. Todo se basa en datos reales (ficha de Maps + la web del negocio si existe).

Reglas de honestidad (CLAUDE.md: "0 falsos positivos"):
  * Cada oportunidad lleva `verificado`: True si se comprobó con datos reales,
    False si es una hipótesis o no se pudo comprobar (web que no responde, bloqueos, etc.).
  * Si una web no se puede leer (bloqueo, JavaScript puro) NO se afirma que le falte medición.
  * La oportunidad "gestion" (app de facturación/gastos) es siempre una hipótesis por tipo
    de negocio: no se puede detectar desde fuera si usan un sistema de gestión.
"""

import ipaddress
import json
import re
import socket
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests

UA = "Mozilla/5.0 (compatible; CazadorLeadsBot/1.0; diagnostico-web)"
MAX_BYTES = 1_500_000
MAX_REDIRECCIONES = 4

# ----------------------------------------------------------------- sectores / ticket

# Ticket estimado: orientativo (lo que un negocio del sector suele poder pagar por un
# proyecto web). Es una heurística de priorización, no un dato medido.
SECTORES = [
    {"nombre": "clínicas", "ticket": "alto"},
    {"nombre": "odontólogos", "ticket": "alto"},
    {"nombre": "inmobiliarias", "ticket": "alto"},
    {"nombre": "abogados", "ticket": "alto"},
    {"nombre": "veterinarias", "ticket": "alto"},
    {"nombre": "talleres mecánicos", "ticket": "medio"},
    {"nombre": "asesorías y contadores", "ticket": "medio"},
    {"nombre": "academias", "ticket": "medio"},
    {"nombre": "hoteles", "ticket": "medio"},
    {"nombre": "restaurantes", "ticket": "bajo"},
    {"nombre": "peluquerías", "ticket": "bajo"},
    {"nombre": "gimnasios", "ticket": "bajo"},
]

_TICKET_ALTO = ("clinic", "clínic", "odontol", "dentist", "inmobiliar", "abogad", "veterinari",
                "estetic", "estétic", "arquitect", "constructor", "psicolog", "psicólog",
                "ortodon", "cirug", "fisioterap", "notari")
_TICKET_BAJO = ("restaurant", "peluquer", "gimnasio", "pizzer", "cafeter", "panader", "barber",
                "heladeri", "comida", "tienda", "licor", "papeler")

# Negocios que suelen llevar citas, cobros y gastos a mano (hipótesis "gestion")
_GESTION = ("clinic", "clínic", "odontol", "dentist", "taller", "asesor", "contab", "abogad",
            "veterinari", "gimnasio", "academia", "inmobiliar", "peluquer", "barber", "spa",
            "estetic", "estétic", "constructor", "psicolog", "psicólog", "fisioterap", "colegio")

# Negocios cuyo cliente reserva o agenda (relevante para "sin_captacion"/gestión)
_AGENDA = ("clinic", "clínic", "odontol", "dentist", "peluquer", "barber", "spa", "estetic",
           "estétic", "veterinari", "psicolog", "psicólog", "fisioterap", "gimnasio", "restaurant")


def _norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def ticket_del_nicho(nicho):
    n = _norm(nicho)
    if any(_norm(k) in n for k in _TICKET_ALTO):
        return "alto"
    if any(_norm(k) in n for k in _TICKET_BAJO):
        return "bajo"
    return "medio"


# ----------------------------------------------------------------- clasificación de la URL

DOMINIOS_WHATSAPP = ("wa.me", "api.whatsapp.com", "whatsapp.com")
DOMINIOS_REDES = ("m.me", "messenger.com", "facebook.com", "fb.com", "instagram.com", "linktr.ee",
                  "tiktok.com", "twitter.com", "x.com", "youtube.com", "beacons.ai")
DOMINIOS_DIRECTORIO = ("paginasamarillas", "doctoralia", "tripadvisor", "yelp.", "mercadolibre",
                       "olx.", "booking.com", "cylex", "guiaempresas", "infoisinfo", "waze.com",
                       "sites.google.com", "maps.google", "g.page", "goo.gl", "bit.ly", "tel:")


def clasificar_url(url):
    """'ninguna' | 'whatsapp' | 'red' | 'directorio' | 'business_site' | 'propia'"""
    if not url:
        return "ninguna"
    host = urlparse(url if "//" in url else "//" + url).netloc.lower() or url.lower()
    if host.endswith("business.site"):
        return "business_site"  # webs gratuitas de Google Business (descontinuadas)
    if any(host == d or host.endswith("." + d) for d in DOMINIOS_WHATSAPP):
        return "whatsapp"
    if any(host == d or host.endswith("." + d) for d in DOMINIOS_REDES) or "linktree" in host:
        return "red"
    if any(d in host or d in url.lower() for d in DOMINIOS_DIRECTORIO):
        return "directorio"
    return "propia"


# ----------------------------------------------------------------- descarga segura

def url_segura(url):
    """Evita SSRF: solo http(s) hacia IPs públicas."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        for info in socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80)):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                    or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except (socket.gaierror, ValueError, OSError):
        return False


def descargar(url, timeout=(5, 9)):
    """Descarga la portada. Devuelve dict con estado: ok | bloqueado | error | insegura."""
    if "//" not in url:
        url = "http://" + url
    inicio = time.time()
    actual = url
    try:
        for _ in range(MAX_REDIRECCIONES + 1):
            if not url_segura(actual):
                return {"estado": "insegura", "url_final": actual, "detalle": "Dirección no permitida"}
            r = requests.get(actual, headers={"User-Agent": UA, "Accept-Language": "es"},
                             timeout=timeout, allow_redirects=False, stream=True)
            if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
                destino = r.headers.get("Location")
                r.close()
                if not destino:
                    break
                actual = urljoin(actual, destino)
                continue
            trozos, total = [], 0
            for c in r.iter_content(65536):
                trozos.append(c)
                total += len(c)
                if total > MAX_BYTES:
                    break
            html = b"".join(trozos).decode(r.encoding or "utf-8", errors="replace")
            ms = int((time.time() - inicio) * 1000)
            r.close()
            if r.status_code in (401, 403, 429, 503) or (
                    r.status_code >= 400 and re.search(r"cloudflare|captcha|access denied", html[:4000], re.I)):
                return {"estado": "bloqueado", "status": r.status_code, "url_final": actual, "tiempo_ms": ms,
                        "detalle": "El sitio no deja leer la página automáticamente"}
            if r.status_code >= 400:
                return {"estado": "error", "status": r.status_code, "url_final": actual, "tiempo_ms": ms,
                        "detalle": f"La web responde con error {r.status_code}"}
            return {"estado": "ok", "status": r.status_code, "html": html, "url_final": actual, "tiempo_ms": ms}
        return {"estado": "error", "url_final": actual, "detalle": "Demasiadas redirecciones"}
    except requests.exceptions.SSLError:
        return {"estado": "error", "url_final": actual, "ssl_error": True, "detalle": "Certificado HTTPS inválido"}
    except requests.exceptions.Timeout:
        return {"estado": "error", "url_final": actual, "detalle": "La web no responde (tiempo agotado)"}
    except requests.exceptions.RequestException as e:
        return {"estado": "error", "url_final": actual, "detalle": f"No se pudo abrir la web ({type(e).__name__})"}


# ----------------------------------------------------------------- análisis del HTML

_FIRMAS_MEDICION = {
    "meta_pixel": (r"connect\.facebook\.net/[^\"'\s]*fbevents\.js", r"\bfbq\s*\(\s*['\"]init['\"]"),
    "gtm": (r"googletagmanager\.com/gtm\.js", r"\bGTM-[A-Z0-9]{4,}\b"),
    "ga4": (r"googletagmanager\.com/gtag/js\?id=G-", r"['\"]G-[A-Z0-9]{8,}['\"]"),
    "google_ads": (r"\bAW-\d{6,}\b", r"googleadservices\.com/pagead/conversion", r"googleads\.g\.doubleclick\.net"),
    "tiktok": (r"analytics\.tiktok\.com", r"\bttq\.load\b"),
    "linkedin": (r"snap\.licdn\.com/li\.lms-analytics",),
    "hotjar": (r"static\.hotjar\.com",),
    "clarity": (r"clarity\.ms/tag",),
}
_SCHEMA_LOCAL = re.compile(
    r"application/ld\+json[^>]*>.*?\"@type\"\s*:\s*\[?\s*\"(LocalBusiness|Dentist|MedicalClinic|Physician|"
    r"VeterinaryCare|AutoRepair|RealEstateAgent|LegalService|Restaurant|HealthClub|BeautySalon|HairSalon|"
    r"Store|Hotel|LodgingBusiness|ProfessionalService|AccountingService|EducationalOrganization)",
    re.I | re.S)
_AGENDA_WEB = re.compile(r"calendly|agenda[rs]?\b|reserv(a|ar)\b|reserva online|booking|citas? online|"
                         r"pide tu cita|solicita(r)? (tu )?cita|simplybook|setmore|doctoralia", re.I)
_FORM_O_WA = re.compile(r"<form\b|wa\.me/|api\.whatsapp\.com|whatsapp|tel:|mailto:", re.I)


def analizar_html(html, ciudad=""):
    h = html or ""
    bajo = h.lower()
    med = {k: any(re.search(p, h, re.I) for p in pats) for k, pats in _FIRMAS_MEDICION.items()}
    titulo = (re.search(r"<title[^>]*>(.*?)</title>", h, re.I | re.S) or [None, ""])[1].strip()
    texto_visible = re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", h, flags=re.I | re.S)
    texto_visible = re.sub(r"\s+", " ", texto_visible).strip()
    ciudad_n = _norm(ciudad.split(",")[0]) if ciudad else ""
    return {
        "medicion": med,
        "titulo": titulo[:160],
        "viewport": bool(re.search(r"<meta[^>]+name=[\"']viewport[\"']", h, re.I)),
        "meta_descripcion": bool(re.search(r"<meta[^>]+name=[\"']description[\"'][^>]*content=[\"'][^\"']{20,}", h, re.I)),
        "h1": bool(re.search(r"<h1\b", h, re.I)),
        "schema_local": bool(_SCHEMA_LOCAL.search(h)),
        "titulo_con_ciudad": bool(ciudad_n and ciudad_n in _norm(titulo)),
        "mapa_embebido": "google.com/maps/embed" in bajo or "maps.google.com/maps" in bajo,
        "telefono_clicable": "tel:" in bajo,
        "tiene_form_o_whatsapp": bool(_FORM_O_WA.search(h)),
        "agenda_online": bool(_AGENDA_WEB.search(texto_visible)),
        # Páginas que se pintan con JavaScript: el HTML inicial casi no trae contenido y
        # las etiquetas de medición pueden cargarse después -> no se puede afirmar nada.
        "solo_js": len(texto_visible) < 250 and bool(re.search(r"id=[\"'](root|app|__next|__nuxt)[\"']", h, re.I)),
    }


def escanear_web(url, ciudad=""):
    """Descarga y analiza una web. Siempre devuelve un dict (nunca lanza)."""
    d = descargar(url)
    out = {"url": url, "estado": d["estado"], "url_final": d.get("url_final"),
           "detalle": d.get("detalle"), "tiempo_ms": d.get("tiempo_ms"), "status": d.get("status"),
           "https": str(d.get("url_final", "")).startswith("https://"), "ssl_error": d.get("ssl_error", False)}
    if d["estado"] == "ok":
        out.update(analizar_html(d.get("html", ""), ciudad))
    return out


def escanear_varias(urls, ciudad="", hilos=8):
    """{url: resultado} en paralelo."""
    urls = list(dict.fromkeys(urls))
    if not urls:
        return {}
    with ThreadPoolExecutor(max_workers=min(hilos, len(urls))) as ex:
        return dict(zip(urls, ex.map(lambda u: escanear_web(u, ciudad), urls)))


# ----------------------------------------------------------------- evaluación

# Orden de prioridad como "ángulo principal" del mensaje + peso para el score
OPORTUNIDADES = {
    "sin_web":       {"peso": 30, "servicio": "desarrollo web",                  "titulo": "Sin página web"},
    "web_mala":      {"peso": 20, "servicio": "rediseño y desarrollo web",       "titulo": "Web con problemas"},
    "sin_medicion":  {"peso": 15, "servicio": "medición y píxeles para anuncios", "titulo": "Sin medición para Ads"},
    "sin_captacion": {"peso": 10, "servicio": "ajustes de captación en la web",  "titulo": "La web no capta contactos"},
    "seo_local":     {"peso": 10, "servicio": "SEO local",                       "titulo": "SEO local débil"},
    "reputacion":    {"peso": 8,  "servicio": "gestión de reseñas",              "titulo": "Reputación mejorable"},
    "gestion":       {"peso": 8,  "servicio": "app de facturación y gastos",     "titulo": "Posible app de gestión"},
}
ORDEN_ANGULOS = list(OPORTUNIDADES)


def _opp(tipo, detalle, verificado=True, parcial=False):
    meta = OPORTUNIDADES[tipo]
    peso = meta["peso"] * (0.5 if parcial else 1) * (1 if verificado else 0.6)
    return {"tipo": tipo, "titulo": meta["titulo"], "servicio": meta["servicio"], "detalle": detalle,
            "verificado": verificado, "peso": round(peso, 1)}


def evaluar(neg, escaneo=None):
    """
    neg: nombre, telefono, whatsapp, redes_sociales, email, rating, resenas, horario, nicho,
         ciudad, clase_web, url, competidores_con_web
    escaneo: resultado de escanear_web() o None.
    Devuelve {oportunidades, diagnostico, score, prioridad, ticket}.
    """
    clase = neg.get("clase_web") or clasificar_url(neg.get("url"))
    nicho, ciudad = neg.get("nicho", ""), neg.get("ciudad", "")
    rating, resenas = neg.get("rating"), neg.get("resenas")
    opps = []
    diag = {"clase_web": clase, "escaneo": None, "seo_local": [], "medicion": None}

    # --- Sin web / solo redes / solo directorio
    if clase in ("ninguna", "whatsapp", "red", "directorio"):
        extra = {"red": " (solo tiene redes sociales: depende de una plataforma ajena)",
                 "whatsapp": " (solo publica un enlace de WhatsApp)",
                 "directorio": " (solo aparece en un directorio de terceros)"}.get(clase, "")
        opps.append(_opp("sin_web", "No tiene página web propia" + extra))

    # --- Con web: revisar calidad, medición, captación
    web = escaneo if clase in ("propia", "business_site") else None
    if clase == "business_site":
        opps.append(_opp("web_mala", "Su web es un sitio gratuito de Google Business (business.site), "
                                     "servicio que Google retiró"))
    if web:
        diag["escaneo"] = {k: web.get(k) for k in (
            "estado", "detalle", "https", "viewport", "tiempo_ms", "titulo", "meta_descripcion", "h1",
            "schema_local", "mapa_embebido", "telefono_clicable", "tiene_form_o_whatsapp", "solo_js",
            "agenda_online", "url_final")}
        diag["medicion"] = web.get("medicion")
        if web["estado"] == "ok":
            fallos = []
            if not web["https"] or web.get("ssl_error"):
                fallos.append("no usa HTTPS seguro")
            if not web["viewport"]:
                fallos.append("no está adaptada a móvil")
            if (web.get("tiempo_ms") or 0) > 4000:
                fallos.append(f"tarda {web['tiempo_ms'] / 1000:.1f} s en responder (medido desde nuestro servidor)")
            graves = [f for f in fallos if "HTTPS" in f or "móvil" in f]
            if graves or len(fallos) >= 2:
                opps.append(_opp("web_mala", "Su web " + " y ".join(fallos)))

            if web.get("solo_js"):
                diag["medicion_nota"] = "La web se pinta con JavaScript: no se puede afirmar qué etiquetas tiene."
            else:
                m = web.get("medicion", {})
                ads_listo = m.get("meta_pixel") or m.get("google_ads") or m.get("tiktok")
                if not any(m.get(k) for k in ("meta_pixel", "ga4", "gtm", "google_ads", "tiktok")):
                    opps.append(_opp("sin_medicion", "No se detecta Google Analytics, píxel de Meta ni etiqueta "
                                                     "de Google Ads/Tag Manager en su web"))
                elif not ads_listo and not m.get("gtm"):
                    opps.append(_opp("sin_medicion", "Tiene analítica pero no píxel de Meta ni de Google Ads: "
                                                     "no puede hacer remarketing ni medir anuncios", parcial=True))
            if not web.get("tiene_form_o_whatsapp"):
                opps.append(_opp("sin_captacion", "La web no muestra formulario, teléfono ni botón de WhatsApp"))
        else:
            # No se pudo leer: nada se afirma como hecho
            if web["estado"] in ("error",):
                opps.append(_opp("web_mala", f"{web.get('detalle') or 'La web no responde'}: confirmar abriéndola",
                                 verificado=False))

    # --- SEO local (datos de Maps + web si se pudo leer)
    seo = []
    if resenas is not None and resenas < 30:
        seo.append(f"solo {resenas} reseñas en Google")
    if rating is None and resenas in (None, 0):
        seo.append("sin reseñas visibles en Google")
    if not neg.get("horario"):
        seo.append("sin horario publicado en su ficha")
    if web and web["estado"] == "ok":
        if not web.get("schema_local"):
            seo.append("su web no tiene datos estructurados de negocio local")
        if not web.get("titulo_con_ciudad"):
            seo.append("el título de su web no menciona la ciudad")
        if not web.get("meta_descripcion"):
            seo.append("su web no tiene meta descripción")
        if not web.get("mapa_embebido"):
            seo.append("su web no tiene el mapa de Google")
    diag["seo_local"] = seo
    if len(seo) >= 2:
        opps.append(_opp("seo_local", "; ".join(seo).capitalize()))

    # --- Reputación
    if rating is not None and rating < 4.2 and (resenas or 0) >= 5:
        opps.append(_opp("reputacion", f"Valoración de {str(rating).replace('.', ',')}★ con {resenas} reseñas"))

    # --- Gestión (hipótesis por tipo de negocio)
    n = _norm(nicho + " " + (neg.get("tipo") or ""))
    if any(_norm(k) in n for k in _GESTION) and not (web and web.get("agenda_online")):
        opps.append(_opp("gestion", "Hipótesis: negocios de este tipo suelen llevar citas, cobros y gastos entre "
                                    "WhatsApp y Excel. Confirmarlo en la primera conversación", verificado=False))

    opps.sort(key=lambda o: ORDEN_ANGULOS.index(o["tipo"]))
    ticket = ticket_del_nicho(nicho)
    score = calcular_score(neg, opps, ticket)
    prioridad = "alta" if score >= 70 else "media" if score >= 45 else "baja"
    return {"oportunidades": opps, "diagnostico": diag, "score": score, "prioridad": prioridad, "ticket": ticket}


def calcular_score(neg, opps, ticket):
    s = 0
    r, rating = neg.get("resenas") or 0, neg.get("rating") or 0
    s += 25 if r >= 200 else 20 if r >= 100 else 15 if r >= 50 else 10 if r >= 20 else 5 if r >= 5 else 0
    s += 10 if rating >= 4.5 else 5 if rating >= 4.2 else 0
    s += min(45, sum(o["peso"] for o in opps))
    s += 5 if neg.get("telefono") else 0
    s += 5 if neg.get("whatsapp") else 0
    s += 5 if neg.get("email") else 0
    s += {"alto": 10, "medio": 5}.get(ticket, 0)
    if any(o["tipo"] == "sin_web" for o in opps) and (neg.get("competidores_con_web") or 0) >= 2:
        s += 5
    return int(min(100, round(s)))


def resumen_json(obj):
    return json.dumps(obj, ensure_ascii=False)
