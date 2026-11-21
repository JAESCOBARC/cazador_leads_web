# -*- coding: utf-8 -*-
"""
Textos de los mensajes (módulo «Contacto») y imagen de firma. No usa IA.

Hay un texto por cada combinación ángulo × paso × variante (A/B): 7 × 3 × 2 = 42, más cuatro piezas
generales (saludo y firma de email y de WhatsApp). Los textos originales viven aquí, en el código;
lo que edites en la app se guarda en la base de datos y tiene prioridad. «Restaurar» borra tu versión.

Los textos llevan variables entre llaves ({nombre}, {ciudad}…) que se sustituyen por datos reales del lead.
Solo se admiten las variables de VARIABLES: nada se evalúa ni se ejecuta (es una sustitución de texto).
"""

import re
import time

from sqlalchemy import delete, func, insert, select, update

import db

ANGULOS = ["sin_web", "web_mala", "sin_medicion", "sin_captacion", "seo_local", "reputacion", "gestion"]
PASOS = {0: "Mensaje inicial", 1: "Seguimiento (+3 días)", 2: "Cierre (+4 días)"}
VARIANTES = ("a", "b")
GLOBALES = {
    "global:saludo_email": "Saludo del email",
    "global:saludo_whatsapp": "Saludo de WhatsApp",
    "global:firma_email": "Firma del email",
    "global:firma_whatsapp": "Firma de WhatsApp",
}

# nombre -> (explicación, ejemplo)
VARIABLES = {
    "nombre": ("Nombre del negocio", "Clínica Dental Sol"),
    "nicho": ("Tipo de negocio", "clínicas dentales"),
    "ciudad": ("Ciudad buscada", "Cali"),
    "dominio": ("Dirección de su web, sin https", "clinicasol.co"),
    "datos_maps": ("Valoración y reseñas de Google Maps (vacío si no hay)", "4,6★ (120 reseñas)"),
    "con_datos": ("Igual que datos_maps pero con « con » delante (vacío si no hay)", " con 4,6★ (120 reseñas)"),
    "competidores": ("Competidores con web que encontramos (vacío si no hay)", "Dental Uno y Dental Dos ya tienen web."),
    "solo_redes": ("«Hoy solo tienen redes sociales» u otra aclaración (vacío si no aplica)", "Hoy solo tienen redes sociales."),
    "servicio": ("Servicio del ángulo elegido", "desarrollo web"),
    "detalle_web": ("Lo que encontró el escáner en su web", "no usa HTTPS ni se adapta al móvil"),
    "hallazgo_web": ("Frase completa sobre su web, ya redactada (cambia si no pudimos abrirla)", "entré a la web de Clínica Dental Sol (clinicasol.co) y encontré que no usa HTTPS."),
    "hallazgo_web_movil": ("Variante de la anterior, «desde mi móvil»", "revisé clinicasol.co desde mi móvil y encontré que no usa HTTPS."),
    "impacto_web": ("Consecuencia de una web con problemas, ya redactada", "Google penaliza ese tipo de webs y el cliente que entra desde el móvil se va rápido."),
    "hallazgo_medicion": ("Frase completa sobre la medición (analítica y píxeles)", "revisé la web de Clínica Dental Sol (clinicasol.co) y no encontré Google Analytics ni píxel de Meta o de Google Ads."),
    "seo_lista": ("Hasta 3 puntos débiles de su SEO local, separados por «;»", "tiene solo 12 reseñas; no publica horario"),
    "remitente": ("Tu nombre (Ajustes → Remitente y firma)", "Laura Gómez"),
    "cargo": ("Tu cargo", "Consultora web"),
    "agencia": ("El nombre de tu agencia", "Estudio Norte"),
    "contacto": ("Tu email o teléfono de contacto", "laura@estudionorte.co"),
    "caso": ("Tu caso de éxito, si lo definiste (vacío si no)", "Un caso reciente: una clínica de Cali pasó de 4 a 15 citas."),
    "asunto_inicial": ("Asunto del mensaje inicial (solo en el asunto de los seguimientos)", "Clínica Dental Sol: sin web = clientes que se van"),
    "cta": ("Tu llamada a la acción (pestaña «Enlaces y CTA»): agenda y WhatsApp. Vacía si no configuraste enlaces", "Reserva aquí: https://cal.com/tu-nombre"),
    "enlace_agenda": ("Tu enlace de agenda de llamadas (vacío si no lo configuraste)", "https://cal.com/tu-nombre"),
    "enlace_whatsapp": ("Tu enlace de WhatsApp (vacío si no lo configuraste)", "https://wa.me/573001234567"),
}
# Variables que no tienen sentido en el asunto
SOLO_CUERPO = ("cta", "enlace_agenda", "enlace_whatsapp")

_QUIEN = "En {agencia} trabajamos con {nicho} ayudándoles a conseguir más clientes."
_CIERRE0 = "¿Tiene sentido explorar si aplica a tu caso?\n¿Tienes 20 minutos esta semana?\n{cta}"

# ángulo -> (apertura A, apertura B, impacto, propuesta, asunto A, asunto B, dato nuevo del seguimiento)
_ORIGINAL = {
    "sin_web": (
        "Vi que aparecen en Google Maps{con_datos}, pero sin página web propia. {solo_redes}",
        "Busqué {nicho} en {ciudad} y encontré {nombre}{con_datos}, pero sin web propia. {solo_redes}",
        "{competidores} Quien los busca en Google y no encuentra web suele llamar al siguiente.",
        "Lo hacemos a través de desarrollo web: una página que aparezca en Google y reciba contactos por WhatsApp.",
        "{nombre}: sin web = clientes que se van a la competencia", "{nombre}: encontré tu ficha pero no tu web",
        "Una web sencilla se publica en pocos días."),
    "web_mala": (
        "{hallazgo_web}", "{hallazgo_web_movil}", "{impacto_web}",
        "Lo hacemos a través de rediseño y desarrollo web: rápida, segura y pensada para móvil.",
        "{nombre}: tu web actual te está costando clientes", "{nombre}: revisé {dominio}",
        "Corregir lo que te comenté no implica empezar de cero."),
    "sin_medicion": (
        "{hallazgo_medicion}",
        "Entré a {dominio} y no detecté ninguna etiqueta de medición instalada.",
        "Sin eso, si invierten en anuncios no saben de dónde viene cada contacto ni pueden volver a mostrarlos a quien ya visitó la web.",
        "Lo hacemos a través de la instalación de medición: Google Tag Manager, píxeles y eventos de contacto.",
        "{nombre}: tu web no mide de dónde vienen los clientes", "{nombre}: antes de invertir en anuncios",
        "La instalación de medición se hace en un día y no toca el diseño."),
    "sin_captacion": (
        "Entré a la web de {nombre} ({dominio}) y no vi formulario, teléfono ni botón de WhatsApp.",
        "Abrí {dominio} y no encontré cómo contactarlos desde la web.",
        "Quien entra con ganas de escribir y no encuentra cómo, se va.",
        "Lo hacemos a través de ajustes en tu web: botón de WhatsApp, formulario y teléfono visibles.",
        "{nombre}: tu web no deja contactar fácil", "{nombre}: cómo contactarte desde {dominio}",
        "Es un cambio pequeño: un botón y un formulario."),
    "seo_local": (
        "Busqué {nicho} en {ciudad} y encontré {nombre}, pero {seo_lista}.",
        "Revisé la ficha de {nombre} en Google Maps y vi que {seo_lista}.",
        'Eso influye en quién aparece primero cuando alguien busca "cerca de mí".',
        "Lo hacemos a través de SEO local: ficha de Google, reseñas y datos de tu web ordenados.",
        "{nombre}: cómo aparecer antes en Google Maps", "{nombre}: revisé tu ficha de Google",
        "Empezar por la ficha de Google da resultados sin tocar nada más."),
    "reputacion": (
        "Vi que {nombre} tiene {datos_maps} en Google Maps.",
        "Revisé las reseñas de {nombre}: {datos_maps}.",
        "Muchos clientes descartan un negocio por debajo de 4,2 antes de llamar.",
        "Lo hacemos a través de un sistema simple para pedir reseñas y responder las que ya tienes.",
        "{nombre}: tus reseñas en Google", "{nombre}: una idea para subir tu valoración",
        "Responder las reseñas existentes ya mejora cómo te ve quien te busca."),
    "gestion": (
        "Hablando con {nicho} me cuentan que llevan citas, cobros y gastos entre WhatsApp y Excel. ¿Es así en {nombre}?",
        "Pregunta rápida sobre {nombre}: ¿cómo llevan hoy la facturación y los gastos?",
        "Cuando todo está en cuadernos y chats, se pierden cobros y se pierde tiempo cada fin de mes.",
        "Lo hacemos a través de una app a medida de facturación y gastos, sencilla de usar.",
        "{nombre}: facturación y gastos sin Excel", "{nombre}: una pregunta sobre tu facturación",
        "Con 15 minutos te muestro cómo se vería con tus propios datos."),
}


def _construir_originales():
    d = {}
    for ang, (ap_a, ap_b, impacto, propuesta, asu_a, asu_b, extra) in _ORIGINAL.items():
        for var, ap, asu in (("a", ap_a, asu_a), ("b", ap_b, asu_b)):
            d[f"{ang}:0:{var}"] = {"asunto": asu, "cuerpo": f"{ap}\n\n{impacto}\n\n{_QUIEN} {propuesta}\n\n{{caso}}\n\n{_CIERRE0}"}
        d[f"{ang}:1:a"] = {"asunto": "Re: {asunto_inicial}",
                           "cuerpo": f"Te escribí hace unos días sobre {{servicio}} para {{nombre}}. {extra}\n\n¿Lo vemos 15 minutos esta semana?\n{{cta}}"}
        d[f"{ang}:1:b"] = {"asunto": "Re: {asunto_inicial}",
                           "cuerpo": f"Retomo mi mensaje sobre {{servicio}} para {{nombre}}. {extra}\n\n¿Te va bien una llamada de 15 minutos esta semana?\n{{cta}}"}
        d[f"{ang}:2:a"] = {"asunto": "Re: {asunto_inicial}",
                           "cuerpo": "Último mensaje sobre {servicio} para {nombre}. Si ahora no es prioridad, sin problema: si más adelante te sirve, aquí estoy.\n\n{cta}"}
        d[f"{ang}:2:b"] = {"asunto": "Re: {asunto_inicial}",
                           "cuerpo": "Cierro aquí lo de {servicio} para {nombre}. Si ahora no es el momento, sin problema; si más adelante te interesa, escríbeme y lo retomamos.\n\n{cta}"}
    d["global:saludo_email"] = {"asunto": None, "cuerpo": "Hola,"}
    d["global:saludo_whatsapp"] = {"asunto": None, "cuerpo": "*Hola {nombre}*"}
    d["global:firma_email"] = {"asunto": None, "cuerpo": "{remitente}\n{cargo} — {agencia}\n{contacto}"}
    d["global:firma_whatsapp"] = {"asunto": None, "cuerpo": "{remitente} — {agencia}\n{contacto}"}
    return d


ORIGINALES = _construir_originales()


class PlantillaError(Exception):
    pass


# ------------------------------------------------------------------ sustitución de variables
_VAR = re.compile(r"\{([a-z_]+)\}")
_LLAVES = re.compile(r"\{([^{}\n]{0,40})\}")


def render(texto, valores, capitalizar=True):
    """Sustituye {variables}. Sin evaluar nada. Quita espacios y líneas que queden vacías, y pone
    mayúscula inicial a los párrafos que empiezan con una variable (que suelen ir en minúscula)."""
    partes = []
    for p in re.split(r"\n\s*\n", (texto or "").replace("\r", "")):
        cap = p.lstrip().startswith("{")
        r = _VAR.sub(lambda m: str(valores.get(m.group(1), m.group(0))), p)
        lineas = [re.sub(r"[ \t]+", " ", ln).strip() for ln in r.split("\n")]
        r = "\n".join(ln for ln in lineas if ln)
        if not r:
            continue
        if cap and capitalizar and r[0].isalpha():
            r = r[0].upper() + r[1:]
        partes.append(r)
    return "\n\n".join(partes)


def render_linea(texto, valores):
    return re.sub(r"\s+", " ", _VAR.sub(lambda m: str(valores.get(m.group(1), m.group(0))), texto or "")).strip()


def validar(clave, asunto, cuerpo):
    """Devuelve (asunto, cuerpo) limpios o lanza PlantillaError con un mensaje claro."""
    if clave not in ORIGINALES:
        raise PlantillaError("Plantilla desconocida")
    es_global = clave.startswith("global:")
    cuerpo = str(cuerpo or "").replace("\r", "").strip()
    asunto = re.sub(r"\s+", " ", str(asunto or "")).strip() if not es_global else None
    if es_global:
        if not 1 <= len(cuerpo) <= 600:
            raise PlantillaError("Este texto debe tener entre 1 y 600 caracteres")
    else:
        if not 20 <= len(cuerpo) <= 3000:
            raise PlantillaError("El mensaje debe tener entre 20 y 3000 caracteres")
        if not 3 <= len(asunto) <= 200:
            raise PlantillaError("El asunto debe tener entre 3 y 200 caracteres")
    pieza = [("asunto", asunto)] if asunto else []
    pieza.append(("mensaje", cuerpo))
    for donde, texto in pieza:
        for m in _LLAVES.finditer(texto):
            nombre = m.group(1)
            if nombre not in VARIABLES:
                raise PlantillaError(f"La variable {{{nombre}}} del {donde} no existe. Usa solo las de la lista.")
            if nombre == "asunto_inicial" and not (donde == "asunto" and not clave.split(":")[1] == "0"):
                raise PlantillaError("{asunto_inicial} solo se puede usar en el asunto de los seguimientos y del cierre")
            if nombre in SOLO_CUERPO and donde == "asunto":
                raise PlantillaError(f"{{{nombre}}} solo se puede usar en el mensaje, no en el asunto")
        if re.search(r"[<>]", texto):
            raise PlantillaError(f"El {donde} no puede llevar < ni >: los correos salen como texto")
    return asunto, cuerpo


# ------------------------------------------------------------------ almacenamiento
_CACHE = {"t": 0.0, "d": None}


def invalidar():
    _CACHE["d"] = None


def _personalizadas():
    if _CACHE["d"] is not None and time.time() - _CACHE["t"] < 30:
        return _CACHE["d"]
    try:
        with db.engine.connect() as conn:
            filas = conn.execute(select(db.plantillas_msg)).mappings().all()
    except Exception as e:  # noqa: BLE001  (si la tabla falla, se usan los textos originales)
        print(f"[PLANTILLAS] No se pudieron leer los textos guardados: {type(e).__name__}")
        _CACHE.update(t=time.time(), d={})
        return {}
    d = {f["clave"]: dict(f) for f in filas if f["clave"] in ORIGINALES}
    _CACHE.update(t=time.time(), d=d)
    return d


def obtener(clave):
    p = _personalizadas().get(clave)
    if p:
        return {"asunto": p["asunto"], "cuerpo": p["cuerpo"]}
    return dict(ORIGINALES[clave])


def globales():
    return {"saludo_email": obtener("global:saludo_email")["cuerpo"], "saludo_whatsapp": obtener("global:saludo_whatsapp")["cuerpo"],
            "firma_email": obtener("global:firma_email")["cuerpo"], "firma_whatsapp": obtener("global:firma_whatsapp")["cuerpo"]}


def estado():
    pers = _personalizadas()
    out = {}
    for clave, orig in ORIGINALES.items():
        p = pers.get(clave)
        actual = {"asunto": p["asunto"], "cuerpo": p["cuerpo"]} if p else orig
        out[clave] = {"asunto": actual["asunto"], "cuerpo": actual["cuerpo"], "personalizada": bool(p),
                      "original": orig, "actualizado_en": p["actualizado_en"].isoformat() if p else None}
    return out


def guardar(clave, asunto, cuerpo, usuario_id=None):
    asunto, cuerpo = validar(clave, asunto, cuerpo)
    with db.engine.begin() as conn:
        existe = conn.execute(select(db.plantillas_msg.c.clave).where(db.plantillas_msg.c.clave == clave)).first()
        vals = dict(asunto=asunto, cuerpo=cuerpo, actualizado_en=db.ahora(), actualizado_por=usuario_id)
        if existe:
            conn.execute(update(db.plantillas_msg).where(db.plantillas_msg.c.clave == clave).values(**vals))
        else:
            conn.execute(insert(db.plantillas_msg).values(clave=clave, **vals))
    invalidar()


def restaurar(clave):
    if clave not in ORIGINALES:
        raise PlantillaError("Plantilla desconocida")
    with db.engine.begin() as conn:
        conn.execute(delete(db.plantillas_msg).where(db.plantillas_msg.c.clave == clave))
    invalidar()


# ------------------------------------------------------------------ llamada a la acción (enlaces de agenda y WhatsApp)
# Los enlaces y los textos se guardan en «ajustes» (claves CTA_*). {cta} = el texto del canal con los enlaces ya puestos.
CTA_DEFECTO = {
    "email": "Reserva aquí un rato conmigo: {enlace_agenda}\nO escríbeme por WhatsApp: {enlace_whatsapp}",
    "whatsapp": "Reserva aquí un rato conmigo: {enlace_agenda}",
}
CTA_VARIABLES = ("enlace_agenda", "enlace_whatsapp", "nombre", "agencia", "remitente")
_CTA_CLAVES = {"agenda": "CTA_AGENDA_URL", "whatsapp": "CTA_WHATSAPP", "texto_email": "CTA_TEXTO_EMAIL", "texto_whatsapp": "CTA_TEXTO_WHATSAPP"}


def _ajustes():
    import ajustes
    return ajustes


def cta_enlaces():
    """Enlaces configurados y válidos: {'agenda': url|'', 'whatsapp': url|''}. Un valor dañado se ignora."""
    aj = _ajustes()
    out = {}
    for k, norm in (("agenda", aj.normalizar_url), ("whatsapp", aj.normalizar_whatsapp)):
        try:
            v = (aj.obtener(_CTA_CLAVES[k]) or "").strip()
            out[k] = norm(v) if v else ""
        except aj.AjusteError:
            out[k] = ""
    return out


def _texto_cta(canal):
    t = (_ajustes().obtener(_CTA_CLAVES["texto_whatsapp" if canal == "whatsapp" else "texto_email"]) or "").strip()
    return t or CTA_DEFECTO["whatsapp" if canal == "whatsapp" else "email"]


def validar_texto_cta(texto, et="El texto"):
    for m in _LLAVES.finditer(texto):
        if m.group(1) not in CTA_VARIABLES:
            raise PlantillaError(f"La variable {{{m.group(1)}}} no se puede usar aquí. Disponibles: " + ", ".join("{" + v + "}" for v in CTA_VARIABLES))
    if re.search(r"[<>]", texto):
        raise PlantillaError(f"«{et}» no puede llevar < ni >: los correos salen como texto")


def render_cta(canal, valores=None, enlaces=None, texto=None):
    """Texto de la llamada a la acción. Una línea que menciona un enlace que no configuraste se omite entera;
    sin ningún enlace queda vacío y el mensaje sale como antes."""
    enlaces = cta_enlaces() if enlaces is None else enlaces
    vals = dict(valores or {}, enlace_agenda=enlaces.get("agenda", ""), enlace_whatsapp=enlaces.get("whatsapp", ""))
    lineas = []
    for ln in (texto if texto is not None else _texto_cta(canal)).replace("\r", "").split("\n"):
        usadas = _VAR.findall(ln)
        if any(u in vals and not vals[u] for u in usadas):
            continue
        r = re.sub(r"[ \t]+", " ", _VAR.sub(lambda m: str(vals.get(m.group(1), m.group(0))), ln)).strip()
        if r:
            lineas.append(r)
    return "\n".join(lineas)


def cta_estado():
    aj = _ajustes()
    en = cta_enlaces()
    return {"agenda": en["agenda"], "whatsapp": en["whatsapp"],
            "texto_email": (aj.obtener("CTA_TEXTO_EMAIL") or "").strip(), "texto_whatsapp": (aj.obtener("CTA_TEXTO_WHATSAPP") or "").strip(),
            "defecto_email": CTA_DEFECTO["email"], "defecto_whatsapp": CTA_DEFECTO["whatsapp"], "variables": list(CTA_VARIABLES)}


def cta_normalizar(d):
    """Valida lo que escribió el usuario y devuelve los cuatro valores normalizados ('' = sin valor). Lanza PlantillaError."""
    aj = _ajustes()
    out = {}
    for k, clave in _CTA_CLAVES.items():
        campo = next(c for c in aj.CAMPOS if c["clave"] == clave)
        try:
            out[k] = aj.validar(campo, (d or {}).get(k))
        except aj.AjusteError as e:
            raise PlantillaError(str(e)) from e
    for k in ("texto_email", "texto_whatsapp"):
        if out[k]:
            validar_texto_cta(out[k], "Texto en el email" if k == "texto_email" else "Texto en WhatsApp")
    return out


def cta_guardar(d, usuario_id=None):
    out = cta_normalizar(d)
    aj = _ajustes()
    try:
        aj.guardar({_CTA_CLAVES[k]: v for k, v in out.items()}, usuario_id=usuario_id)
    except aj.AjusteError as e:
        raise PlantillaError(str(e)) from e


def cta_vista_previa(d, valores=None):
    out = cta_normalizar(d)
    en = {"agenda": out["agenda"], "whatsapp": out["whatsapp"]}
    return {"agenda": out["agenda"], "whatsapp": out["whatsapp"],
            "email": render_cta("email", valores, en, out["texto_email"] or CTA_DEFECTO["email"]),
            "whatsapp_texto": render_cta("whatsapp", valores, en, out["texto_whatsapp"] or CTA_DEFECTO["whatsapp"])}


# ------------------------------------------------------------------ imagen de firma
IMAGEN_MAX_BYTES = 300 * 1024
ANCHO_MIN, ANCHO_MAX = 80, 600
_FIRMAS_IMAGEN = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"))


def tipo_imagen(datos):
    """Tipo según los primeros bytes (no se fía del nombre ni de lo que diga el navegador). SVG no se admite."""
    for firma, tipo in _FIRMAS_IMAGEN:
        if datos.startswith(firma):
            return tipo
    return None


def _ancho_valido(ancho):
    try:
        a = int(ancho)
    except (TypeError, ValueError):
        raise PlantillaError("El ancho debe ser un número")
    if not ANCHO_MIN <= a <= ANCHO_MAX:
        raise PlantillaError(f"El ancho debe estar entre {ANCHO_MIN} y {ANCHO_MAX} píxeles")
    return a


def guardar_imagen(datos, nombre, ancho, usuario_id=None):
    if not datos:
        raise PlantillaError("No se recibió ninguna imagen")
    if len(datos) > IMAGEN_MAX_BYTES:
        raise PlantillaError(f"La imagen pesa {len(datos) // 1024} KB; el máximo es {IMAGEN_MAX_BYTES // 1024} KB. Redúcela o expórtala más pequeña")
    tipo = tipo_imagen(datos)
    if not tipo:
        raise PlantillaError("Formato no admitido: usa PNG, JPG o GIF (SVG y WebP no funcionan en todos los correos)")
    ancho = _ancho_valido(ancho)
    nombre = re.sub(r"[^\w.\- ]", "", str(nombre or "firma"))[:100] or "firma"
    vals = dict(contenido=datos, tipo=tipo, nombre=nombre, ancho=ancho, actualizado_en=db.ahora(), actualizado_por=usuario_id)
    with db.engine.begin() as conn:
        if conn.execute(select(db.firma_imagen.c.id).where(db.firma_imagen.c.id == 1)).first():
            conn.execute(update(db.firma_imagen).where(db.firma_imagen.c.id == 1).values(**vals))
        else:
            conn.execute(insert(db.firma_imagen).values(id=1, **vals))


def cambiar_ancho(ancho):
    ancho = _ancho_valido(ancho)
    with db.engine.begin() as conn:
        r = conn.execute(update(db.firma_imagen).where(db.firma_imagen.c.id == 1).values(ancho=ancho))
    if not r.rowcount:
        raise PlantillaError("Aún no has subido una imagen")


def quitar_imagen():
    with db.engine.begin() as conn:
        conn.execute(delete(db.firma_imagen).where(db.firma_imagen.c.id == 1))


def imagen():
    """La imagen completa (con bytes) o None."""
    with db.engine.connect() as conn:
        f = conn.execute(select(db.firma_imagen).where(db.firma_imagen.c.id == 1)).mappings().first()
    return dict(f) if f else None


def imagen_info():
    with db.engine.connect() as conn:
        f = conn.execute(select(db.firma_imagen.c.tipo, db.firma_imagen.c.nombre, db.firma_imagen.c.ancho,
                                db.firma_imagen.c.actualizado_en, func.length(db.firma_imagen.c.contenido).label("bytes"))
                         .where(db.firma_imagen.c.id == 1)).mappings().first()
    if not f:
        return {"existe": False, "max_kb": IMAGEN_MAX_BYTES // 1024, "ancho_min": ANCHO_MIN, "ancho_max": ANCHO_MAX}
    return {"existe": True, "tipo": f["tipo"], "nombre": f["nombre"], "ancho": f["ancho"], "bytes": f["bytes"],
            "actualizado_en": f["actualizado_en"].isoformat(), "max_kb": IMAGEN_MAX_BYTES // 1024,
            "ancho_min": ANCHO_MIN, "ancho_max": ANCHO_MAX}

