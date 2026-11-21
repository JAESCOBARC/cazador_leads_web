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
        "nombre": os.getenv("REMITENTE_NOMBRE") or "[TU NOMBRE]",
        "cargo": os.getenv("REMITENTE_CARGO") or "[TU CARGO]",
        "agencia": os.getenv("AGENCIA_NOMBRE") or "[TU AGENCIA]",
        "contacto": os.getenv("REMITENTE_CONTACTO") or "[TU EMAIL / TELÉFONO]",
        "caso": (os.getenv("CASO_EXITO") or "").strip(),
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


# ------------------------------------------------------------------ ángulos
# Cada ángulo devuelve (apertura_a, apertura_b, impacto, propuesta, asunto_a, asunto_b)

def _ang_sin_web(l):
    n, datos = l["nombre"], _datos_maps(l)
    clase = (l.get("diagnostico") or {}).get("clase_web")
    con = f" con {datos}" if datos else ""
    solo = {"red": " Hoy solo tienen redes sociales.", "directorio": " Hoy solo aparecen en un directorio."}.get(clase, "")
    comp = _competidores(l)
    ap_a = f"vi que aparecen en Google Maps{con}, pero sin página web propia.{solo}"
    ap_b = (f"busqué {l.get('nicho', 'tu sector')} en {l.get('ciudad', 'tu zona')} y encontré {n}{con}, "
            f"pero sin web propia.{solo}")
    impacto = (comp + " " if comp else "") + "Quien los busca en Google y no encuentra web suele llamar al siguiente."
    return (ap_a, ap_b, impacto.strip(),
            "Lo hacemos a través de desarrollo web: una página que aparezca en Google y reciba contactos por WhatsApp.",
            f"{n}: sin web = clientes que se van a la competencia", f"{n}: encontré tu ficha pero no tu web")


def _ang_web_mala(l):
    n, e = l["nombre"], _escaneo(l)
    dom = _dominio(e.get("url_final") or l.get("web_url"))
    opp = next((o for o in l.get("oportunidades", []) if o["tipo"] == "web_mala"), {})
    detalle = (opp.get("detalle") or "").replace("Su web ", "")
    if opp and not opp.get("verificado", True):
        ap = f"intenté abrir la web de {n} ({dom}) y no logré hacerlo desde mi equipo."
        impacto = "Si a ti también te falla, quien te busca en Google se va a otro negocio."
    else:
        ap = f"entré a la web de {n} ({dom}) y encontré que {detalle}."
        impacto = "Google penaliza ese tipo de webs y el cliente que entra desde el móvil se va rápido."
    return (ap, f"revisé {dom} desde mi móvil y encontré que {detalle}." if detalle else ap, impacto,
            "Lo hacemos a través de rediseño y desarrollo web: rápida, segura y pensada para móvil.",
            f"{n}: tu web actual te está costando clientes", f"{n}: revisé {dom}")


def _ang_sin_medicion(l):
    n, e = l["nombre"], _escaneo(l)
    dom = _dominio(e.get("url_final") or l.get("web_url"))
    opp = next((o for o in l.get("oportunidades", []) if o["tipo"] == "sin_medicion"), {})
    parcial = "remarketing" in (opp.get("detalle") or "")
    if parcial:
        ap = f"revisé la web de {n} ({dom}): tiene analítica, pero no encontré píxel de Meta ni de Google Ads."
    else:
        ap = f"revisé la web de {n} ({dom}) y no encontré Google Analytics ni píxel de Meta o de Google Ads."
    return (ap, f"entré a {dom} y no detecté ninguna etiqueta de medición instalada.",
            "Sin eso, si invierten en anuncios no saben cuántos contactos sale de cada uno ni pueden volver a "
            "mostrarlos a quien ya visitó la web.",
            "Lo hacemos a través de la instalación de medición: Google Tag Manager, píxeles y eventos de contacto.",
            f"{n}: tu web no mide de dónde vienen los clientes", f"{n}: antes de invertir en anuncios")


def _ang_sin_captacion(l):
    n, e = l["nombre"], _escaneo(l)
    dom = _dominio(e.get("url_final") or l.get("web_url"))
    return (f"entré a la web de {n} ({dom}) y no vi formulario, teléfono ni botón de WhatsApp.",
            f"abrí {dom} y no encontré cómo contactarlos desde la web.",
            "Quien entra con ganas de escribir y no encuentra cómo, se va.",
            "Lo hacemos a través de ajustes en tu web: botón de WhatsApp, formulario y teléfono visibles.",
            f"{n}: tu web no deja contactar fácil", f"{n}: cómo contactarte desde {dom}")


def _ang_seo_local(l):
    n, nicho, ciudad = l["nombre"], l.get("nicho", "tu sector"), l.get("ciudad", "tu zona")
    seo = (l.get("diagnostico") or {}).get("seo_local") or []
    lista = "; ".join(seo[:3])
    return (f"busqué {nicho} en {ciudad} y encontré {n}, pero {lista}.",
            f"revisé la ficha de {n} en Google Maps y vi que {lista}.",
            "Eso influye en quién aparece primero cuando alguien busca \"cerca de mí\".",
            "Lo hacemos a través de SEO local: ficha de Google, reseñas y datos de tu web ordenados.",
            f"{n}: cómo aparecer antes en Google Maps", f"{n}: revisé tu ficha de Google")


def _ang_reputacion(l):
    n, datos = l["nombre"], _datos_maps(l)
    return (f"vi que {n} tiene {datos} en Google Maps.",
            f"revisé las reseñas de {n}: {datos}.",
            "Muchos clientes descartan un negocio por debajo de 4,2 antes de llamar.",
            "Lo hacemos a través de un sistema simple para pedir reseñas y responder las que ya tienes.",
            f"{n}: tus reseñas en Google", f"{n}: una idea para subir tu valoración")


def _ang_gestion(l):
    n, nicho = l["nombre"], l.get("nicho", "tu sector")
    return (f"hablando con {nicho} me cuentan que llevan citas, cobros y gastos entre WhatsApp y Excel. "
            f"¿Es así en {n}?",
            f"pregunta rápida sobre {n}: ¿cómo llevan hoy la facturación y los gastos?",
            "Cuando todo está en cuadernos y chats, se pierden cobros y se pierde tiempo cada fin de mes.",
            "Lo hacemos a través de una app a medida de facturación y gastos, sencilla de usar.",
            f"{n}: facturación y gastos sin Excel", f"{n}: una pregunta sobre tu facturación")


_ANGULOS = {"sin_web": _ang_sin_web, "web_mala": _ang_web_mala, "sin_medicion": _ang_sin_medicion,
            "sin_captacion": _ang_sin_captacion, "seo_local": _ang_seo_local,
            "reputacion": _ang_reputacion, "gestion": _ang_gestion}

# Dato nuevo para el primer seguimiento, por ángulo (sin inventar cifras)
_EXTRA_SEG = {
    "sin_web": "Una web sencilla se publica en pocos días.",
    "web_mala": "Corregir lo que te comenté no implica empezar de cero.",
    "sin_medicion": "La instalación de medición se hace en un día y no toca el diseño.",
    "sin_captacion": "Es un cambio pequeño: un botón y un formulario.",
    "seo_local": "Empezar por la ficha de Google da resultados sin tocar nada más.",
    "reputacion": "Responder las reseñas existentes ya mejora cómo te ve quien te busca.",
    "gestion": "Con 15 minutos te muestro cómo se vería con tus propios datos.",
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


def construir(lead, angulo=None, canal=None, paso=0, variante=None):
    """
    lead: dict con nombre, nicho, ciudad, rating, resenas, telefono, whatsapp, email, web_url,
          oportunidades (lista), diagnostico (dict), competidores_nombres (opcional), clave.
    paso: 0 = mensaje inicial, 1 = seguimiento (día +3), 2 = cierre (día +7).
    Devuelve {angulo, canal, paso, variante, asunto, cuerpo, palabras, plantilla}.
    """
    angulo = angulo if angulo in _ANGULOS else (angulo_principal(lead.get("oportunidades")) or "sin_web")
    canal = canal if canal in ("whatsapp", "email", "telefono") else canal_para(lead)
    variante = variante if variante in ("a", "b") else variante_estable(lead.get("clave") or lead["nombre"])
    r = _remitente()
    nombre = lead["nombre"]
    ap_a, ap_b, impacto, propuesta, asu_a, asu_b = _ANGULOS[angulo](lead)
    apertura = ap_a if variante == "a" else ap_b
    asunto = asu_a if variante == "a" else asu_b
    servicio = OPORTUNIDADES[angulo]["servicio"]
    caso = f"Un caso reciente: {r['caso']}" if r["caso"] else ""
    firma_email = f"{r['nombre']}\n{r['cargo']} — {r['agencia']}\n{r['contacto']}"
    firma_wa = f"{r['nombre']} — {r['agencia']}\n{r['contacto']}"
    es_wa = canal != "email"

    if paso == 0:
        quien = f"En {r['agencia']} trabajamos con {lead.get('nicho', 'negocios como el tuyo')} ayudándoles a conseguir más clientes."
        cuerpo_core = "\n\n".join(x for x in (
            apertura[0].upper() + apertura[1:],
            impacto, f"{quien} {propuesta}", caso,
            "¿Tiene sentido explorar si aplica a tu caso?\n¿Tienes 20 minutos esta semana?") if x)
        if es_wa:
            cuerpo = f"*Hola {nombre}*\n\n{cuerpo_core}\n\n{firma_wa}"
            asunto = None
        else:
            cuerpo = f"Hola,\n\n{cuerpo_core}\n\n{firma_email}"
    elif paso == 1:
        cuerpo_core = (f"Te escribí hace unos días sobre {servicio} para {nombre}. {_EXTRA_SEG[angulo]}\n\n"
                       "¿Lo vemos 15 minutos esta semana?")
        cuerpo = (f"*Hola {nombre}*\n\n{cuerpo_core}\n\n{firma_wa}" if es_wa
                  else f"Hola,\n\n{cuerpo_core}\n\n{firma_email}")
        asunto = f"Re: {asunto}" if asunto and not es_wa else None
    else:
        cuerpo_core = (f"Último mensaje sobre {servicio} para {nombre}. Si ahora no es prioridad, sin problema: "
                       "si más adelante te sirve, aquí estoy.")
        cuerpo = (f"*Hola {nombre}*\n\n{cuerpo_core}\n\n{firma_wa}" if es_wa
                  else f"Hola,\n\n{cuerpo_core}\n\n{firma_email}")
        asunto = f"Re: {asunto}" if asunto and not es_wa else None

    return {"angulo": angulo, "canal": canal, "paso": paso, "variante": variante, "asunto": asunto,
            "cuerpo": cuerpo, "palabras": contar_palabras(cuerpo),
            "plantilla": f"{angulo}:{'wa' if es_wa else 'email'}:{variante}"}
