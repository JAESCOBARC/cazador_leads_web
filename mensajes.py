# -*- coding: utf-8 -*-
"""
Generador de mensajes en frío (WhatsApp / email) y secuencia de seguimiento.

Reglas (CLAUDE.md): tuteo, primera persona ("vi", "encontré", "entré a tu web"), un único
servicio por mensaje, máximo 150 palabras, sin hipérboles ni jerga, solo datos verificables.
El "mini-caso" solo aparece si defines CASO_EXITO en .env (un caso REAL tuyo); nunca se inventa.
"""

import os
import re
from urllib.parse import urlparse

import ajustes
import plantillas
from escaner import OPORTUNIDADES, ORDEN_ANGULOS

MAX_PALABRAS = 150
PASOS_DIAS = {0: 3, 1: 4}  # tras el mensaje inicial: +3 días; tras el seguimiento 1: +4 días


def contar_palabras(texto):
    return len(re.findall(r"\S+", texto or ""))


def _num(n):
    return str(n).replace(".", ",")


def _dominio(url):
    host = urlparse(url if "//" in (url or "") else "//" + (url or "")).netloc
    return host.replace("www.", "") or url or "tu web"


def _remitente():
    return {
        "nombre": ajustes.obtener("REMITENTE_NOMBRE") or "[TU NOMBRE]",
        "cargo": ajustes.obtener("REMITENTE_CARGO") or "[TU CARGO]",
        "agencia": ajustes.obtener("AGENCIA_NOMBRE") or "[TU AGENCIA]",
        "contacto": ajustes.obtener("REMITENTE_CONTACTO") or "[TU EMAIL / TELÉFONO]",
        "caso": (ajustes.obtener("CASO_EXITO") or "").strip(),
    }


def _datos_maps(l):
    """Frase con datos reales de la ficha (solo si existen)."""
    r, n = l.get("rating"), l.get("resenas")
    if r and n:
        return f"{_num(r)}★ ({n} reseñas)"
    if n:
        return f"{n} reseñas"
    return ""


def _competidores(l):
    comp = l.get("competidores_nombres") or []
    if not comp:
        return ""
    if len(comp) == 1:
        return f"{comp[0]} ya tiene web."
    return f"{comp[0]} y {comp[1]} ya tienen web."


def _escaneo(l):
    return (l.get("diagnostico") or {}).get("escaneo") or {}


# ------------------------------------------------------------------ variables de los textos
# Los textos (plantillas.py) se editan en el módulo Contacto; aquí se calculan los datos reales del lead
# que sustituyen a las {variables}.

def variables(l, angulo="sin_web", canal="email"):
    r = _remitente()
    n, e = l["nombre"], _escaneo(l)
    dom = _dominio(e.get("url_final") or l.get("web_url"))
    datos = _datos_maps(l)
    clase = (l.get("diagnostico") or {}).get("clase_web")
    opps = l.get("oportunidades") or []

    wm = next((o for o in opps if o["tipo"] == "web_mala"), {})
    detalle = (wm.get("detalle") or "").replace("Su web ", "").strip() or "tiene aspectos por mejorar"
    if wm and not wm.get("verificado", True):
        hallazgo = f"intenté abrir la web de {n} ({dom}) y no logré hacerlo desde mi equipo."
        movil = hallazgo
        impacto = "Si a ti también te falla, quien te busca en Google se va a otro negocio."
    else:
        hallazgo = f"entré a la web de {n} ({dom}) y encontré que {detalle}."
        movil = f"revisé {dom} desde mi móvil y encontré que {detalle}."
        impacto = "Google penaliza ese tipo de webs y el cliente que entra desde el móvil se va rápido."

    sm = next((o for o in opps if o["tipo"] == "sin_medicion"), {})
    if "remarketing" in (sm.get("detalle") or ""):
        medicion = f"revisé la web de {n} ({dom}): tiene analítica, pero no encontré píxel de Meta ni de Google Ads."
    else:
        medicion = f"revisé la web de {n} ({dom}) y no encontré Google Analytics ni píxel de Meta o de Google Ads."

    seo = "; ".join(((l.get("diagnostico") or {}).get("seo_local") or [])[:3]) or "hay aspectos que se pueden mejorar"
    enlaces = plantillas.cta_enlaces()
    cta = plantillas.render_cta("email" if canal == "email" else "whatsapp",
                                {"nombre": n, "agencia": r["agencia"], "remitente": r["nombre"]}, enlaces)
    return {
        "enlace_agenda": enlaces["agenda"], "enlace_whatsapp": enlaces["whatsapp"], "cta": cta,
        "nombre": n, "nicho": l.get("nicho") or "negocios como el tuyo", "ciudad": l.get("ciudad") or "tu zona", "dominio": dom,
        "datos_maps": datos, "con_datos": f" con {datos}" if datos else "", "competidores": _competidores(l),
        "solo_redes": {"red": "Hoy solo tienen redes sociales.", "directorio": "Hoy solo aparecen en un directorio."}.get(clase, ""),
        "servicio": OPORTUNIDADES[angulo]["servicio"], "detalle_web": detalle, "hallazgo_web": hallazgo,
        "hallazgo_web_movil": movil, "impacto_web": impacto, "hallazgo_medicion": medicion, "seo_lista": seo,
        "remitente": r["nombre"], "cargo": r["cargo"], "agencia": r["agencia"], "contacto": r["contacto"],
        "caso": f"Un caso reciente: {r['caso']}" if r["caso"] else "",
    }


def lead_demo(angulo):
    """Negocio de ejemplo para la vista previa del módulo Contacto (datos inventados, solo para ver el formato)."""
    detalles = {"web_mala": "Su web no usa HTTPS ni se adapta al móvil", "sin_medicion": "No tiene analítica ni píxeles"}
    return {
        "nombre": "Clínica Dental Sol", "nicho": "clínicas dentales", "ciudad": "Cali", "rating": 4.6, "resenas": 120,
        "competidores_nombres": ["Dental Uno", "Dental Dos"], "web_url": "https://clinicasol.co",
        "oportunidades": [{"tipo": angulo, "verificado": True, "detalle": detalles.get(angulo, "")}],
        "diagnostico": {"clase_web": "red" if angulo == "sin_web" else "propia", "escaneo": {"url_final": "https://clinicasol.co"},
                        "seo_local": ["tiene solo 12 reseñas", "no publica horario"]},
        "clave": "demo",
    }


def angulo_principal(opps):
    tipos = [o["tipo"] for o in opps or []]
    for a in ORDEN_ANGULOS:
        if a in tipos:
            return a
    return None


def variante_estable(clave):
    """A/B estable por lead (no cambia entre recargas)."""
    return "a" if sum(map(ord, str(clave))) % 2 == 0 else "b"


def canal_para(lead):
    """WhatsApp publicado por el negocio > email real > teléfono (WhatsApp sin confirmar)."""
    if lead.get("whatsapp") and (lead.get("diagnostico") or {}).get("whatsapp_confirmado"):
        return "whatsapp"
    if lead.get("email"):
        return "email"
    if lead.get("whatsapp") or lead.get("telefono"):
        return "whatsapp"
    return "telefono"


def construir(lead, angulo=None, canal=None, paso=0, variante=None, textos=None, piezas=None):
    """
    lead: dict con nombre, nicho, ciudad, rating, resenas, telefono, whatsapp, email, web_url,
          oportunidades (lista), diagnostico (dict), competidores_nombres (opcional), clave.
    paso: 0 = mensaje inicial, 1 = seguimiento (día +3), 2 = cierre (día +7).
    textos / piezas: solo para la vista previa del módulo Contacto (texto sin guardar del mensaje / de saludo y firma).
    Devuelve {angulo, canal, paso, variante, asunto, cuerpo, palabras, plantilla}.
    """
    angulo = angulo if angulo in OPORTUNIDADES else (angulo_principal(lead.get("oportunidades")) or "sin_web")
    canal = canal if canal in ("whatsapp", "email", "telefono") else canal_para(lead)
    variante = variante if variante in ("a", "b") else variante_estable(lead.get("clave") or lead["nombre"])
    paso = paso if paso in (0, 1, 2) else 0
    es_wa = canal != "email"
    vals = variables(lead, angulo, "whatsapp" if es_wa else "email")
    t = textos or plantillas.obtener(f"{angulo}:{paso}:{variante}")
    g = dict(plantillas.globales(), **(piezas or {}))

    inicial = plantillas.obtener(f"{angulo}:0:{variante}")["asunto"] if paso else t["asunto"]
    vals["asunto_inicial"] = plantillas.render_linea(inicial, vals)
    nucleo = plantillas.render(t["cuerpo"], vals)
    saludo = plantillas.render(g["saludo_whatsapp" if es_wa else "saludo_email"], vals, capitalizar=False)
    firma = plantillas.render(g["firma_whatsapp" if es_wa else "firma_email"], vals, capitalizar=False)
    cuerpo = "\n\n".join(x for x in (saludo, nucleo, firma) if x)
    asunto = None if es_wa else plantillas.render_linea(t["asunto"], vals)

    return {"angulo": angulo, "canal": canal, "paso": paso, "variante": variante, "asunto": asunto,
            "cuerpo": cuerpo, "palabras": contar_palabras(cuerpo),
            "plantilla": f"{angulo}:{'wa' if es_wa else 'email'}:{variante}"}


def vista_previa(clave, asunto, cuerpo, canal="email"):
    """Cómo quedaría un texto (sin guardarlo) con un negocio de ejemplo. Valida igual que al guardar."""
    asunto, cuerpo = plantillas.validar(clave, asunto, cuerpo)
    if clave.startswith("global:"):
        pieza = clave.split(":")[1]
        canal = "whatsapp" if pieza.endswith("whatsapp") else "email"
        return construir(lead_demo("sin_web"), "sin_web", canal, 0, "a", piezas={pieza: cuerpo})
    ang, paso, var = clave.split(":")
    return construir(lead_demo(ang), ang, canal, int(paso), var, textos={"asunto": asunto, "cuerpo": cuerpo})
