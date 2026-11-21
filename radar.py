# -*- coding: utf-8 -*-
"""
Radar: orquesta una exploración completa de una ciudad.

  buscar en Maps (paginado, con caché)  ->  escanear las webs existentes  ->  evaluar
  oportunidades  ->  guardar leads (sin duplicar)  ->  devolver ids para pintar en el mapa.

Se ejecuta en un hilo en segundo plano y el navegador consulta el progreso (polling),
porque una exploración puede tardar más que el timeout de una petición web.
"""

import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy import insert, select, update

import db
import escaner
from cazador_leads import CazadorLeads

BASE_DIR = Path(__file__).parent

# cobertura -> (puntos de la cuadrícula, páginas por punto). Créditos SerpAPI = puntos x páginas por sector.
COBERTURAS = {"rapida": (1, 1), "normal": (1, 2), "profunda": (5, 2)}
MAX_SECTORES = 4

JOBS = {}
_lock = threading.Lock()


class CacheDB:
    def get(self, clave):
        return db.cache_get(clave)

    def set(self, clave, datos):
        db.cache_set(clave, datos)


def _entero_env(nombre, defecto):
    try:
        return max(1, int(os.getenv(nombre, defecto)))
    except ValueError:
        return defecto


def creditos_estimados(n_sectores, cobertura):
    puntos, paginas = COBERTURAS.get(cobertura, COBERTURAS["normal"])
    return n_sectores * puntos * paginas


# ------------------------------------------------------------------ trabajos

def iniciar(ciudad, pais, sectores, cobertura, analizar_webs, user_id):
    job_id = uuid.uuid4().hex[:12]
    job = {"id": job_id, "estado": "ejecutando", "etapa": "Preparando el radar…", "progreso": 2,
           "resultado": None, "error": None, "user_id": user_id, "creado": time.time()}
    with _lock:
        for k in [k for k, j in JOBS.items() if time.time() - j["creado"] > 3600]:
            JOBS.pop(k, None)
        JOBS[job_id] = job
    threading.Thread(target=_ejecutar, daemon=True,
                     args=(job, ciudad, pais, sectores, cobertura, analizar_webs)).start()
    return job_id


def estado(job_id):
    return JOBS.get(job_id)


def _set(job, etapa=None, progreso=None):
    if etapa is not None:
        job["etapa"] = etapa
    if progreso is not None:
        job["progreso"] = max(job["progreso"], min(99, int(progreso)))


def _ejecutar(job, ciudad, pais, sectores, cobertura, analizar_webs):
    try:
        puntos, paginas = COBERTURAS.get(cobertura, COBERTURAS["normal"])
        cap_nuevos = _entero_env("MAX_RESULTS", 20)
        cap_scan = _entero_env("MAX_SCAN_WEBS", 40)
        cache = CacheDB()
        advertencias, creditos = [], 0
        grupos = []  # (cazador, negocios)
        sector_cuenta = {}

        # ---- 1. Búsqueda en Maps
        for i, nicho in enumerate(sectores):
            cz = CazadorLeads(base_dir=BASE_DIR)
            cz.nicho, cz.ciudad, cz.pais = nicho, ciudad, pais
            base = 3 + 42 * i / len(sectores)
            span = 42 / len(sectores)

            def prog(p, t, base=base, span=span, nicho=nicho):
                _set(job, f"Escaneando {nicho} en {ciudad} ({p}/{t})…", base + span * p / t)

            _set(job, f"Escaneando {nicho} en {ciudad}…", base)
            negocios = cz.buscar_en_google(paginas=paginas, puntos=puntos, cache=cache, progreso=prog)
            creditos += cz.creditos_usados
            advertencias += cz.advertencias
            if negocios:
                grupos.append((cz, negocios))
            else:
                advertencias.append(f"{nicho}: {cz.error_busqueda or 'sin resultados'}")
                if cz.error_busqueda and ("SERPAPI_KEY" in cz.error_busqueda or "ubicación" in cz.error_busqueda):
                    raise RuntimeError(cz.error_busqueda)
        if not grupos:
            raise RuntimeError(advertencias[-1] if advertencias else "Google Maps no devolvió negocios.")

        # ---- 2. Escaneo de las webs existentes
        escaneos = {}
        if analizar_webs:
            candidatos = sorted(
                [n for _, ns in grupos for n in ns if n["clase_web"] == "propia"],
                key=lambda n: -(n.get("resenas") or 0))
            urls = list(dict.fromkeys(n["url"] for n in candidatos))[:cap_scan]
            if len(candidatos) > len(urls):
                advertencias.append(f"Solo se analizaron {len(urls)} webs de {len(candidatos)} (límite por exploración).")
            hechos = 0
            with ThreadPoolExecutor(max_workers=8) as ex:
                futuros = {ex.submit(escaner.escanear_web, u, ciudad): u for u in urls}
                for f in as_completed(futuros):
                    escaneos[futuros[f]] = f.result()
                    hechos += 1
                    _set(job, f"Analizando webs ({hechos}/{len(urls)})…", 45 + 40 * hechos / max(1, len(urls)))

        # ---- 3. Evaluar y seleccionar
        _set(job, "Detectando oportunidades…", 87)
        existentes = _claves_existentes()
        a_guardar, total_negocios = [], 0
        mejor = {}  # clave -> lead: un negocio puede salir en varios sectores; se queda el de mayor score
        for cz, negocios in grupos:
            total_negocios += len(negocios)
            con_web = [n for n in negocios if n["tiene_web"]]
            comp = [n["nombre"] for n in sorted(con_web, key=lambda n: -(n.get("resenas") or 0))][:2]
            leads = []
            for n in negocios:
                lead = cz.preparar_lead(n, 0, escaneo=escaneos.get(n.get("url")),
                                        competidores_nombres=comp, competidores_con_web=len(con_web))
                lead["diagnostico"]["competidores_nombres"] = comp
                lead["clave"] = db.clave_lead(lead["nombre"], _limpio(lead["telefono"]), ciudad)
                if lead["oportunidades"]:
                    leads.append(lead)
            leads.sort(key=lambda l: -l["score"])
            nuevos = 0
            for l in leads:
                previo = mejor.get(l["clave"])
                if previo is not None:
                    if l["score"] > previo["score"]:
                        a_guardar[a_guardar.index(previo)] = l
                        mejor[l["clave"]] = l
                    continue
                if l["clave"] in existentes:
                    pass  # se refresca el diagnóstico, no cuenta para el tope
                elif nuevos < cap_nuevos:
                    nuevos += 1
                else:
                    continue
                mejor[l["clave"]] = l
                a_guardar.append(l)
            sector_cuenta[cz.nicho] = {"nicho": cz.nicho, "ticket": escaner.ticket_del_nicho(cz.nicho),
                                       "encontrados": len(negocios), "con_oportunidad": len(leads)}

        # ---- 4. Guardar
        _set(job, "Guardando leads…", 94)
        guardados = guardar_leads(a_guardar, job["user_id"])
        job["resultado"] = {
            "ciudad": ciudad, "pais": pais, "cobertura": cobertura,
            "centro": ({"lat": grupos[0][0].geo["lat"], "lon": grupos[0][0].geo["lon"]}
                       if grupos[0][0].geo else None),
            "total_negocios": total_negocios, "creditos_usados": creditos,
            "sectores": list(sector_cuenta.values()),
            "lead_ids": [g["id"] for g in guardados], "nuevos": sum(1 for g in guardados if not g["repetido"]),
            "advertencias": advertencias,
        }
        job.update(estado="listo", etapa="Radar completado", progreso=100)
    except Exception as e:  # noqa: BLE001 - se informa al usuario
        import traceback
        traceback.print_exc()
        job.update(estado="error", error=str(e), etapa="Error")


# ------------------------------------------------------------------ persistencia

def _limpio(v):
    v = (v or "").strip()
    return "" if v.upper() == "N/A" else v


def _claves_existentes():
    with db.engine.connect() as conn:
        return {r[0] for r in conn.execute(select(db.leads.c.clave))}


def _columnas_diagnostico(l):
    return dict(
        rating=l.get("rating"), resenas=l.get("resenas"), tipo=(l.get("tipo") or "")[:160],
        lat=l.get("lat"), lon=l.get("lon"), web_url=(l.get("web_url") or "")[:500],
        tiene_web=l.get("tiene_web"), maps_url=(l.get("maps_url") or "")[:500], score=l.get("score"),
        prioridad=l.get("prioridad"), ticket=l.get("ticket"), competidores=l.get("competidores"),
        oportunidades=json.dumps(l.get("oportunidades") or [], ensure_ascii=False),
        diagnostico=json.dumps(l.get("diagnostico") or {}, ensure_ascii=False),
        escaneado_en=db.ahora(),
    )


def guardar_leads(leads, user_id=None):
    """Inserta leads nuevos y refresca el diagnóstico de los ya existentes (sin tocar su estado,
    asignación ni notas). Devuelve, por posición, {id, estado, repetido}."""
    salida = []
    with db.engine.begin() as conn:
        for l in leads:
            clave = l["clave"]
            existente = conn.execute(select(db.leads.c.id, db.leads.c.estado)
                                     .where(db.leads.c.clave == clave)).first()
            cols = _columnas_diagnostico(l)
            if existente:
                if existente.estado == "nuevo":  # aún sin contactar: mensaje al día
                    cols.update(asunto=l.get("asunto") or "", cuerpo=l.get("cuerpo") or "",
                                canal_recomendado=l.get("canal_recomendado"), plantilla=l.get("plantilla"))
                conn.execute(update(db.leads).where(db.leads.c.id == existente.id)
                             .values(**cols, actualizado_en=db.ahora()))
                salida.append({"id": existente.id, "estado": existente.estado, "repetido": True})
                continue
            res = conn.execute(insert(db.leads).values(
                clave=clave, nombre=l["nombre"], telefono=_limpio(l.get("telefono")),
                email=l.get("email_real") or "", whatsapp=l.get("whatsapp") or "",
                redes_sociales=l.get("redes_sociales") or "", direccion=_limpio(l.get("direccion")),
                nicho=l["nicho"], ciudad=l["ciudad"], pais=l["pais"],
                canal_recomendado=l.get("canal_recomendado"), asunto=l.get("asunto") or "",
                cuerpo=l.get("cuerpo") or "", plantilla=l.get("plantilla"), estado="nuevo",
                creado_en=db.ahora(), actualizado_en=db.ahora(), **cols))
            salida.append({"id": res.inserted_primary_key[0], "estado": "nuevo", "repetido": False})
    return salida


def lead_desde_fila(r):
    """Reconstruye el dict que espera mensajes.construir() a partir de una fila de la BD."""
    def j(v, defecto):
        try:
            return json.loads(v) if v else defecto
        except ValueError:
            return defecto
    diag = j(r["diagnostico"], {})
    return {
        "clave": r["clave"], "nombre": r["nombre"], "nicho": r["nicho"], "ciudad": r["ciudad"],
        "telefono": r["telefono"], "whatsapp": r["whatsapp"], "email": r["email"],
        "rating": r["rating"], "resenas": r["resenas"], "web_url": r["web_url"],
        "oportunidades": j(r["oportunidades"], []), "diagnostico": diag,
        "competidores_nombres": diag.get("competidores_nombres", []),
    }
