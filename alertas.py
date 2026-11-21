# -*- coding: utf-8 -*-
"""
Aviso por email cuando el consumo mensual de búsquedas de SerpAPI llega a un umbral (por defecto 80%).

  * Se revisa tras cada consumo registrado (y cuando se consulta la cuenta real de SerpAPI).
  * Un mismo umbral avisa UNA sola vez por mes (tabla alertas_enviadas); si el envío falla, se reintenta
    más tarde sin marcarlo como enviado.
  * Si el consumo salta varios umbrales a la vez, se manda un solo correo.
  * Base del cálculo: lo mayor entre lo que registró esta app y lo que informa la cuenta real de SerpAPI.
"""

import os
import threading
import time
from datetime import datetime

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError

import ajustes
import correo
import db

_lock = threading.Lock()
_real = {"t": 0.0, "d": None}      # última respuesta de la cuenta real (la actualiza app.py)
_ultimo_fallo = {"t": 0.0}
_ultima_prueba = {"t": 0.0}
REINTENTO_TRAS_FALLO = 600          # segundos
REAL_VIGENTE = 3600


def recordar_cuenta(datos):
    _real.update(t=time.time(), d=datos)


def cuota_configurada():
    try:
        return max(1, int(ajustes.obtener("SERPAPI_CUOTA_MES", "100") or 100))
    except ValueError:
        return 100


def umbrales():
    out = []
    for v in (ajustes.obtener("ALERTA_UMBRALES", "80") or "80").split(","):
        try:
            n = int(v.strip())
        except ValueError:
            continue
        if 1 <= n <= 200:
            out.append(n)
    return sorted(set(out)) or [80]


def _mes():
    a = db.ahora()
    return f"{a.year}-{a.month:02d}", datetime(a.year, a.month, 1), a


def situacion():
    """Consumo del mes (UTC): lo registrado por la app, lo que informa SerpAPI y la cuota efectiva."""
    clave, inicio, ahora = _mes()
    C = db.consumo
    with db.engine.connect() as conn:
        usados, ahorrados = conn.execute(select(func.coalesce(func.sum(C.c.creditos), 0), func.coalesce(func.sum(C.c.ahorrados), 0))
                                         .where(C.c.fecha >= inicio)).one()
        por_tipo = {t: n for t, n in conn.execute(select(C.c.tipo, func.sum(C.c.creditos)).where(C.c.fecha >= inicio).group_by(C.c.tipo))}
        ciudades = conn.execute(select(C.c.ciudad, func.sum(C.c.creditos).label("n")).where(C.c.fecha >= inicio)
                                .group_by(C.c.ciudad).order_by(func.sum(C.c.creditos).desc()).limit(3)).all()
    real = _real["d"] if (_real["d"] and time.time() - _real["t"] < REAL_VIGENTE and _real["d"].get("disponible")) else None
    usados_real = (real or {}).get("usadas") or 0
    cuota = (real or {}).get("cuota") or cuota_configurada()
    total = max(int(usados), int(usados_real))
    dias_mes = (datetime(ahora.year + (ahora.month == 12), ahora.month % 12 + 1, 1) - inicio).days
    return {"mes": clave, "usados_app": int(usados), "usados_real": int(usados_real) if real else None, "usados": total,
            "cuota": int(cuota), "ahorrados": int(ahorrados), "por_tipo": {k: int(v) for k, v in por_tipo.items()},
            "ciudades": [(c or "—", int(n)) for c, n in ciudades], "porcentaje": total / cuota * 100,
            "proyeccion": round(total / ahora.day * dias_mes), "dias_restantes": dias_mes - ahora.day}


def _app_url():
    return (os.getenv("APP_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")


def construir_mensaje(umbral, s, prueba=False):
    pct = round(s["porcentaje"])
    restantes = max(0, s["cuota"] - s["usados"])
    agotada = s["usados"] >= s["cuota"]
    titulo = ("Ya agotaste" if agotada else f"Ya usaste el {pct}% de") + " tus búsquedas de SerpAPI de este mes"
    asunto = f"{'[PRUEBA] ' if prueba else ''}Cazador Leads: {titulo[0].lower() + titulo[1:]} ({s['usados']} de {s['cuota']})"
    lineas = [
        f"{'PRUEBA DEL AVISO · ' if prueba else ''}{titulo}.",
        "",
        f"  Usadas:      {s['usados']} de {s['cuota']} ({pct}%)",
        f"  Disponibles: {restantes}",
        f"  Proyección a fin de mes: {s['proyeccion']} (quedan {s['dias_restantes']} días)",
        f"  Ahorradas por caché este mes: {s['ahorrados']}",
    ]
    if s["por_tipo"]:
        lineas.append("  Por tipo: " + ", ".join(f"{'Radar (Maps)' if k == 'radar' else 'Búsqueda de redes'} {v}" for k, v in s["por_tipo"].items()))
    if s["ciudades"]:
        lineas.append("  Ciudades que más gastaron: " + ", ".join(f"{c} ({n})" for c, n in s["ciudades"]))
    lineas += ["", "Para estirar lo que queda:",
               "  - Usa la cobertura «Rápida» (1 crédito por sector) y deja la «Profunda» (hasta 10) para zonas clave.",
               "  - Repetir una búsqueda no gasta: se sirve desde la caché durante 7 días.",
               "  - En el lote de redes, fija un tope bajo de créditos.",
               "  - Si necesitas más, sube de plan en SerpAPI y ajusta SERPAPI_CUOTA_MES."]
    if _app_url():
        lineas += ["", f"Panel: {_app_url()}/#analitica"]
    if prueba:
        lineas += ["", "Este es un correo de prueba: confirma que los avisos llegan a este buzón."]
    lineas += ["", f"Aviso configurado al {umbral}% de la cuota. Se envía una vez por mes y umbral."]
    texto = "\n".join(lineas)
    html = ("<div style=\"font-family:system-ui,Segoe UI,sans-serif;max-width:520px;color:#0b0b0b\">"
            + "".join(f"<p style='margin:0 0 6px'>{_esc(l) if l else '&nbsp;'}</p>" for l in lineas) + "</div>").replace("  ", "&nbsp;&nbsp;")
    return asunto, texto, html


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def revisar():
    """Comprueba el umbral y avisa si corresponde. Nunca lanza: un fallo de correo no debe romper una búsqueda."""
    try:
        _revisar()
    except Exception as e:  # noqa: BLE001
        print(f"[ALERTA] No se pudo revisar el umbral: {correo.limpiar(e)}")


def _revisar():
    if not correo.configurado():
        return
    s = situacion()
    cruzados = [u for u in umbrales() if s["porcentaje"] >= u]
    if not cruzados:
        return
    if time.time() - _ultimo_fallo["t"] < REINTENTO_TRAS_FALLO:
        return
    with _lock:
        nuevos = []
        for u in cruzados:
            try:
                with db.engine.begin() as conn:
                    conn.execute(insert(db.alertas_enviadas).values(clave=f"{s['mes']}:{u}", umbral=u, enviada_en=db.ahora(),
                                                                     usados=s["usados"], cuota=s["cuota"]))
                nuevos.append(u)
            except IntegrityError:
                pass  # ya se avisó de este umbral este mes
        if not nuevos:
            return
        try:
            asunto, texto, html = construir_mensaje(max(nuevos), s)
            correo.enviar(asunto, texto, html)
            print(f"[ALERTA] Aviso enviado: {s['usados']} de {s['cuota']} ({round(s['porcentaje'])}%)")
        except Exception as e:  # noqa: BLE001
            _ultimo_fallo["t"] = time.time()
            with db.engine.begin() as conn:  # se libera la marca para reintentar más tarde
                for u in nuevos:
                    conn.execute(delete(db.alertas_enviadas).where(db.alertas_enviadas.c.clave == f"{s['mes']}:{u}"))
            print(f"[ALERTA] Falló el envío, se reintentará: {correo.limpiar(e)}")


def enviar_prueba():
    """Correo de prueba (admin). Limita a un envío cada 30 s. Lanza CorreoError si falla."""
    if time.time() - _ultima_prueba["t"] < 30:
        raise correo.CorreoError("Espera unos segundos antes de enviar otra prueba")
    asunto, texto, html = construir_mensaje(umbrales()[0], situacion(), prueba=True)
    correo.enviar(asunto, texto, html)
    _ultima_prueba["t"] = time.time()


def estado():
    clave, _, _ = _mes()
    with db.engine.connect() as conn:
        enviadas = conn.execute(select(db.alertas_enviadas).where(db.alertas_enviadas.c.clave.like(f"{clave}:%"))
                                .order_by(db.alertas_enviadas.c.enviada_en)).mappings().all()
    return {"configurado": correo.configurado(), "proveedor": correo.proveedor(),
            "destinos": [correo.enmascarar(d) for d in correo.destinatarios()], "umbrales": umbrales(),
            "enviadas_mes": [{"umbral": e["umbral"], "fecha": e["enviada_en"].isoformat(), "usados": e["usados"], "cuota": e["cuota"]} for e in enviadas]}
