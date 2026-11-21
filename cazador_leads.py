#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cazador Leads Web — Prospección Automatizada de Negocios sin Página Web
Busca negocios reales en Google Maps (vía SerpAPI), filtra los que no tienen
página web y genera emails personalizados. No genera ni completa con datos
simulados/inventados bajo ninguna circunstancia.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import ajustes
import mensajes
from escaner import clasificar_url, evaluar, ocultar_clave

try:
    import requests
except ImportError:
    print("⚠️  Instala las dependencias: pip install -r requirements.txt")
    exit(1)


def _user_agent():
    """User-Agent genérico. Nominatim pide un contacto en el User-Agent: si quieres
    incluirlo, defínelo tú en la variable de entorno NOMINATIM_CONTACTO (no se guarda en el código)."""
    contacto = os.getenv("NOMINATIM_CONTACTO", "").strip()
    return f"CazadorLeadsWeb/1.0 ({contacto})" if contacto else "CazadorLeadsWeb/1.0"


class CazadorLeads:
    _cache_geo = {}  # compartido entre instancias: evita repetir geocodificaciones

    def __init__(self, base_dir="."):
        self.base_dir = Path(base_dir)
        self.nicho_file = self.base_dir / "nicho.txt"
        self.ciudad_file = self.base_dir / "ciudad.txt"
        self.pais_file = self.base_dir / "pais.txt"
        self.output_file = self.base_dir / "prospects_encontrados.md"

        self.nicho = ""
        self.ciudad = ""
        self.pais = ""
        self.localizacion = ""  # Combinación de ciudad, país
        self.leads = []
        self.error_busqueda = None
        self.advertencias = []
        self.creditos_usados = 0
        self.consultas_cache = 0  # consultas servidas desde la caché (crédito ahorrado)
        self.geo = None
        self.ya_guardado = None  # función opcional: negocio -> bool (omite leads ya guardados)

        try:
            self.max_results = int(os.getenv("MAX_RESULTS", "10"))
        except ValueError:
            self.max_results = 10
        if self.max_results < 1:
            self.max_results = 10

    def leer_inputs(self):
        """Lee los archivos de entrada"""
        try:
            with open(self.nicho_file, 'r', encoding='utf-8') as f:
                self.nicho = f.read().strip()
            with open(self.ciudad_file, 'r', encoding='utf-8') as f:
                self.ciudad = f.read().strip()
            with open(self.pais_file, 'r', encoding='utf-8') as f:
                self.pais = f.read().strip()

            # Combinar localización
            self.localizacion = f"{self.ciudad}, {self.pais}" if self.ciudad and self.pais else ""

            if not self.nicho or not self.ciudad or not self.pais:
                print("❌ Error: Nicho, ciudad o país vacíos")
                return False

            print(f"✓ Nicho: {self.nicho}")
            print(f"✓ Ciudad: {self.ciudad}")
            print(f"✓ País: {self.pais}")
            print(f"✓ Localización: {self.localizacion}")
            return True
        except FileNotFoundError as e:
            print(f"❌ Archivo no encontrado: {e}")
            return False

    # Palabras de relleno que la gente suele escribir antes del nombre propio de un
    # barrio/zona (ej. "barrio Corales") pero que Nominatim no entiende como
    # calificador — busca el texto tal cual y no encuentra nada. Se eliminan antes
    # de geocodificar.
    _PALABRAS_RELLENO_UBICACION = (
        "barrio", "sector", "colonia", "urbanización", "urbanizacion", "urb.", "urb",
        "vereda", "corregimiento", "conjunto residencial", "comuna"
    )

    def _limpiar_texto_ubicacion(self, texto):
        """Quita palabras de relleno tipo 'barrio'/'sector' de un texto de ubicación."""
        limpio = texto
        for palabra in self._PALABRAS_RELLENO_UBICACION:
            limpio = re.sub(rf"\b{re.escape(palabra)}\b", "", limpio, flags=re.IGNORECASE)
        limpio = re.sub(r"\s+", " ", limpio).strip(" ,")
        return limpio or texto  # si queda vacío, mejor conservar el original

    def geocodificar(self, ciudad, pais):
        """Convierte ciudad+país en coordenadas GPS reales usando Nominatim (OpenStreetMap).
        Esto es necesario porque SerpAPI's engine=google_maps requiere coordenadas (ll),
        no acepta un nombre de ciudad como texto libre, y además resuelve correctamente
        ciudades homónimas en distintos países (ej. Madrid, Colombia vs Madrid, España)."""
        ciudad_limpia = self._limpiar_texto_ubicacion(ciudad)
        if ciudad_limpia != ciudad:
            print(f"   ℹ️ Ubicación simplificada para la búsqueda: '{ciudad}' → '{ciudad_limpia}'")

        # Intenta primero con el texto limpio; si no encuentra nada y se había
        # modificado el texto, reintenta con el original (por si el nombre real
        # del lugar sí incluye esa palabra, ej. "Sector Los Andes").
        intentos = [ciudad_limpia]
        if ciudad_limpia != ciudad:
            intentos.append(ciudad)

        for intento in intentos:
            clave = f"{intento}, {pais}".lower()
            if clave in self._cache_geo:
                return self._cache_geo[clave]

            geo = None
            try:
                geo = self._geocodificar_nominatim(clave)
            except requests.RequestException as e:
                print(f"   ⚠️ Nominatim falló ({e}); probando Photon...")
                geo = self._geocodificar_photon(clave)

            if geo:
                self._cache_geo[clave] = geo
                return geo

        return None

    def _geocodificar_nominatim(self, consulta):
        """Nominatim con reintentos ante 429 (límite de 1 req/s, IPs compartidas como Render)."""
        url = "https://nominatim.openstreetmap.org/search"
        headers = {"User-Agent": _user_agent()}
        params = {"q": consulta, "format": "json", "limit": 1}

        for espera in (0, 2, 5):
            if espera:
                time.sleep(espera)
            response = requests.get(url, params=params, headers=headers, timeout=15)
            if response.status_code == 429:
                continue
            response.raise_for_status()
            resultados = response.json()
            if resultados:
                return {
                    "lat": float(resultados[0]["lat"]),
                    "lon": float(resultados[0]["lon"]),
                    "display_name": resultados[0]["display_name"]
                }
            return None
        raise requests.RequestException("429 Too many requests (reintentos agotados)")

    def _geocodificar_photon(self, consulta):
        """Geocodificador alternativo (Photon/komoot, también basado en OpenStreetMap)."""
        response = requests.get(
            "https://photon.komoot.io/api/",
            params={"q": consulta, "limit": 1},
            headers={"User-Agent": _user_agent()},
            timeout=15,
        )
        response.raise_for_status()
        features = response.json().get("features", [])
        if not features:
            return None
        lon, lat = features[0]["geometry"]["coordinates"]
        p = features[0].get("properties", {})
        nombre = ", ".join(x for x in (p.get("name"), p.get("state"), p.get("country")) if x)
        return {"lat": float(lat), "lon": float(lon), "display_name": nombre or consulta}

    # Desplazamientos (en grados, ~2,7 km) para cubrir varios barrios además del centro
    _OFFSETS = [(0, 0), (0.025, 0), (-0.025, 0), (0, 0.025), (0, -0.025),
                (0.025, 0.025), (0.025, -0.025), (-0.025, 0.025), (-0.025, -0.025)]

    def _consultar_serpapi(self, serpapi_key, query, lat, lon, start, cache):
        """Una consulta a Google Maps (SerpAPI) con caché: si ya se hizo, no gasta crédito."""
        clave = f"gm|{query.lower()}|{lat:.4f},{lon:.4f}|{start}"
        if cache is not None:
            guardado = cache.get(clave)
            if guardado:
                self.consultas_cache += 1
                return json.loads(guardado), True
        params = {"engine": "google_maps", "type": "search", "q": query,
                  "ll": f"@{lat},{lon},14z", "api_key": serpapi_key}
        if start:
            params["start"] = start
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            # "sin resultados" no es un fallo: simplemente no hay más páginas
            if "hasn't returned any results" in str(data["error"]) or "no results" in str(data["error"]).lower():
                return {"local_results": []}, False
            raise RuntimeError(f"SerpAPI: {data['error']}")
        if cache is not None:
            cache.set(clave, json.dumps({k: data.get(k) for k in ("local_results", "place_results")},
                                        ensure_ascii=False))
        self.creditos_usados += 1
        return data, False

    def buscar_en_google(self, paginas=None, puntos=1, cache=None, progreso=None):
        """Busca negocios REALES en Google Maps vía SerpAPI. No genera ni completa
        con datos simulados bajo ninguna circunstancia: si la búsqueda falla o no hay
        resultados, se retorna una lista vacía junto con self.error_busqueda explicando por qué.

        paginas: páginas de ~20 resultados por punto (por defecto env MAPS_PAGINAS o 1).
        puntos:  1 = centro de la ciudad; 5 = centro + 4 barrios; 9 = cuadrícula completa.
        cache:   objeto con get(clave)/set(clave, texto) para no repetir consultas pagadas.
        """
        self.error_busqueda = None
        self.advertencias = []
        self.creditos_usados = 0
        self.consultas_cache = 0
        query = self.nicho.strip()
        if paginas is None:
            try:
                paginas = int(os.getenv("MAPS_PAGINAS", "1"))
            except ValueError:
                paginas = 1
        paginas = max(1, min(int(paginas), 3))
        puntos = max(1, min(int(puntos), len(self._OFFSETS)))

        print(f"\n🔍 Buscando: '{query}' en {self.ciudad}, {self.pais}")

        serpapi_key = ajustes.obtener("SERPAPI_KEY")
        if not serpapi_key or serpapi_key == "tu_api_key_aqui":
            self.error_busqueda = "SERPAPI_KEY no configurada en .env"
            print(f"   ❌ {self.error_busqueda}")
            return []

        # 1. Geocodificar ciudad+país -> coordenadas reales (desambigua ciudades homónimas)
        try:
            print(f"   📍 Geocodificando '{self.ciudad}, {self.pais}'...")
            geo = self.geocodificar(self.ciudad, self.pais)
        except Exception as e:
            self.error_busqueda = f"Error al geocodificar ubicación: {e}"
            print(f"   ❌ {self.error_busqueda}")
            return []

        if not geo:
            self.error_busqueda = f"No se pudo encontrar la ubicación '{self.ciudad}, {self.pais}'. Verifica que esté bien escrita."
            print(f"   ❌ {self.error_busqueda}")
            return []

        print(f"   ✓ Ubicación resuelta: {geo['display_name']}")
        self.geo = geo

        # 2. Consultar Google Maps (varios puntos x varias páginas), sin duplicados
        vistos, lugares = set(), []
        total_pasos = puntos * paginas
        paso = 0
        try:
            for dlat, dlon in self._OFFSETS[:puntos]:
                for pag in range(paginas):
                    paso += 1
                    if progreso:
                        progreso(paso, total_pasos)
                    try:
                        data, _ = self._consultar_serpapi(serpapi_key, query, geo["lat"] + dlat,
                                                          geo["lon"] + dlon, pag * 20, cache)
                    except (requests.exceptions.RequestException, RuntimeError) as e:
                        if not lugares:
                            raise
                        self.advertencias.append(f"Una consulta falló y se devuelven resultados parciales: {ocultar_clave(e)}")
                        break
                    resultados = data.get("local_results") or []
                    if not resultados and data.get("place_results"):
                        resultados = [data["place_results"]]  # búsqueda con un único resultado
                    nuevos = 0
                    for p in resultados:
                        k = p.get("place_id") or (p.get("title"), p.get("address"))
                        if k in vistos:
                            continue
                        vistos.add(k)
                        lugares.append(p)
                        nuevos += 1
                    if len(resultados) < 20 or not nuevos:
                        break  # no hay más páginas útiles en este punto
        except requests.exceptions.RequestException as e:
            self.error_busqueda = f"Error de conexión con SerpAPI: {ocultar_clave(e)}"
            print(f"   ❌ {self.error_busqueda}")
            return []
        except RuntimeError as e:
            self.error_busqueda = ocultar_clave(e)
            print(f"   ❌ {self.error_busqueda}")
            return []
        except Exception as e:
            self.error_busqueda = f"Error inesperado: {e}"
            print(f"   ❌ {self.error_busqueda}")
            import traceback
            traceback.print_exc()
            return []

        print(f"   📊 Negocios reales encontrados: {len(lugares)} ({self.creditos_usados} créditos usados)")

        negocios = []
        for place in lugares:
            nombre = place.get("title", "")
            if not nombre:
                continue
            website = place.get("website", "") or ""
            clase = clasificar_url(website)
            place_id = place.get("place_id", "")
            gps = place.get("gps_coordinates") or {}
            tipo = place.get("type") or ", ".join(place.get("types") or [])
            negocios.append({
                "nombre": nombre,
                "telefono": place.get("phone", ""),
                "whatsapp": website if clase == "whatsapp" else None,
                "redes_sociales": website if clase == "red" else None,
                "email": None,  # SerpAPI/Google Maps no expone emails; nunca se inventa
                "direccion": place.get("address", ""),
                "clase_web": clase,
                # Solo cuenta como web propia una web real (los directorios/redes/WhatsApp no)
                "tiene_web": clase in ("propia", "business_site"),
                "url": website,
                "maps_url": f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else "",
                "rating": place.get("rating"),
                "resenas": place.get("reviews"),
                "tipo": tipo,
                "horario": place.get("hours") or place.get("operating_hours") or "",
                "lat": gps.get("latitude"),
                "lon": gps.get("longitude"),
            })
            print(f"      {nombre}: {clase} ({website or 'sin sitio listado'})")

        if not negocios:
            self.error_busqueda = "Google Maps no retornó negocios para esta búsqueda."
        return negocios

    def filtrar_sin_web(self, resultados):
        """Filtra solo negocios SIN página web - máximo self.max_results (config. vía MAX_RESULTS en .env).
        Los que ya están guardados se descartan ANTES de cortar, para que repetir una
        búsqueda no devuelva siempre los mismos."""
        sin_web = [r for r in resultados if not r.get("tiene_web", True)]
        total_sin_web = len(sin_web)
        if self.ya_guardado:
            sin_web = [r for r in sin_web if not self.ya_guardado(r)]
            print(f"✓ Ya guardados (omitidos): {total_sin_web - len(sin_web)}")
        print(f"\n✓ Total encontrados: {len(resultados)}")
        print(f"✓ Con web: {len(resultados) - total_sin_web}")
        print(f"✓ SIN web (leads nuevos): {len(sin_web)}")
        return sin_web[:self.max_results]

    def extraer_email_contacto(self, negocio):
        """Retorna el email SOLO si viene verificado desde la fuente real.
        Nunca se inventa ni se adivina un email."""
        return negocio.get("email") or None

    def _telefono_a_whatsapp(self, telefono):
        """Construye un link wa.me a partir de un teléfono REAL verificado en Maps.
        No está confirmado que ese número use WhatsApp, por eso se marca aparte de un
        wa.me que el propio negocio publicó en su ficha."""
        if not telefono or telefono == "N/A":
            return None
        digitos = re.sub(r"\D", "", telefono)
        if len(digitos) < 8:  # muy corto para ser un número real completo
            return None
        return f"https://wa.me/{digitos}"

    def preparar_lead(self, negocio, numero, escaneo=None, competidores_nombres=None, competidores_con_web=0):
        """Evalúa las oportunidades del negocio y genera su mensaje (ángulo principal,
        canal real disponible). Devuelve el lead listo para guardar/mostrar."""
        telefono = negocio.get("telefono") or "N/A"
        # Contactos publicados por el propio negocio en su web (portada, contacto, aviso legal)
        contactos = (escaneo or {}).get("contactos") or {}
        email_web = (contactos.get("emails") or [{}])[0].get("valor")
        wa_web = (contactos.get("whatsapps") or [{}])[0].get("link")

        whatsapp = negocio.get("whatsapp") or wa_web
        whatsapp_confirmado = bool(whatsapp)  # publicado por el negocio (Maps o su web)
        if not whatsapp:
            whatsapp = self._telefono_a_whatsapp(telefono)
        email = self.extraer_email_contacto(negocio) or email_web

        neg = dict(negocio, nicho=self.nicho, ciudad=self.ciudad, competidores_con_web=competidores_con_web,
                   email=email)
        ev = evaluar(neg, escaneo)
        ev["diagnostico"]["contactos"] = contactos
        if negocio.get("clase_web") == "red" and escaneo:
            ev["diagnostico"]["red_social"] = {k: escaneo.get(k) for k in ("url", "estado", "descripcion", "detalle")}
        ev["diagnostico"]["whatsapp_confirmado"] = whatsapp_confirmado

        lead = {
            "numero": numero, "nombre": negocio["nombre"], "telefono": telefono, "whatsapp": whatsapp,
            "whatsapp_confirmado": whatsapp_confirmado, "redes_sociales": negocio.get("redes_sociales"),
            "email": email or "No disponible (Google Maps no lo publica — verificar manualmente)",
            "email_real": email, "direccion": negocio.get("direccion") or "N/A",
            "maps_url": negocio.get("maps_url", ""), "rating": negocio.get("rating"),
            "resenas": negocio.get("resenas"), "tipo": negocio.get("tipo"), "lat": negocio.get("lat"),
            "lon": negocio.get("lon"), "web_url": negocio.get("url") or "", "tiene_web": negocio.get("tiene_web"),
            "competidores": competidores_con_web, "oportunidades": ev["oportunidades"],
            "diagnostico": ev["diagnostico"], "score": ev["score"], "prioridad": ev["prioridad"],
            "ticket": ev["ticket"], "nicho": self.nicho, "ciudad": self.ciudad, "pais": self.pais,
        }
        msg = self.generar_mensaje_personalizado(dict(
            lead, competidores_nombres=competidores_nombres or [],
            telefono=telefono if telefono != "N/A" else "", email=email,
            clave=negocio["nombre"] + self.ciudad))
        lead.update(canal_recomendado=msg["canal"], asunto=msg["asunto"], cuerpo=msg["cuerpo"],
                    plantilla=msg["plantilla"], angulo=msg["angulo"])
        return lead

    def generar_mensaje_personalizado(self, lead, numero=None, paso=0):
        """Mensaje para el ángulo principal del lead usando solo datos reales (ver mensajes.py)."""
        return mensajes.construir(lead, paso=paso)

    def ejecutar(self):
        """Ejecuta el flujo completo"""
        print("=" * 60)
        print("🎯 CAZADOR LEADS WEB — PROSPECCIÓN AUTOMATIZADA")
        print("=" * 60)

        # 1. Leer inputs
        if not self.leer_inputs():
            return False

        # 2. Buscar en Google
        resultados = self.buscar_en_google()

        # 3. Filtrar sin web
        self.leads = self.filtrar_sin_web(resultados)

        if not self.leads:
            if self.error_busqueda:
                print(f"❌ No se encontraron negocios sin web: {self.error_busqueda}")
            else:
                print("❌ No se encontraron negocios sin web (todos los encontrados ya tienen web)")
            return False

        # 4. Generar mensajes personalizados (WhatsApp/email/teléfono según lo real disponible)
        print("\n📧 Generando mensajes personalizados...")
        emails_generados = []
        con_web = [r for r in resultados if r.get("tiene_web")]
        nombres_comp = [r["nombre"] for r in sorted(con_web, key=lambda r: -(r.get("resenas") or 0))][:2]
        for i, lead in enumerate(self.leads, 1):
            email_data = self.preparar_lead(lead, i, competidores_nombres=nombres_comp,
                                            competidores_con_web=len(con_web))
            emails_generados.append(email_data)
            print(f"   ✓ Lead {i}: {lead['nombre']} (canal: {email_data['canal_recomendado']})")

        # 5. Guardar output
        self.guardar_output(emails_generados)

        print(f"\n✅ Prospección completada: {len(emails_generados)} leads")
        print(f"📄 Output guardado en: {self.output_file}")
        return True

    def guardar_output(self, emails):
        """Guarda los leads y emails en archivo markdown"""
        fecha = datetime.now().strftime("%d de %B de %Y")

        contenido = f"""# Prospects Encontrados — {self.nicho.title()}

**Localización:** {self.localizacion}
**Fecha:** {fecha}
**Total de leads:** {len(emails)}

---

"""

        for email_data in emails:
            canal = email_data["canal_recomendado"]

            if canal == "whatsapp":
                canal_label = (
                    "💬 WhatsApp (publicado por el negocio en Maps)"
                    if email_data["whatsapp_confirmado"]
                    else "💬 WhatsApp (generado desde el teléfono — verificar que tenga WhatsApp antes de enviar)"
                )
            elif canal == "email":
                canal_label = "📧 Email"
            else:
                canal_label = "☎️ Solo teléfono (sin WhatsApp ni email — llamar directamente)"

            contacto_directo = ""
            if canal == "whatsapp":
                contacto_directo = f"**WhatsApp:** {email_data['whatsapp']}\n"
            if email_data.get("redes_sociales"):
                contacto_directo += f"**Red social:** {email_data['redes_sociales']}\n"

            asunto_linea = f"**Asunto:** {email_data['asunto']}\n\n---\n\n" if email_data['asunto'] else ""
            titulos_mensaje = {
                "whatsapp": "### Mensaje para WhatsApp",
                "email": "### Email Personalizado",
                "telefono": "### Mensaje sugerido (sin WhatsApp/email confirmado — usar como guion telefónico o buscar el canal manualmente)"
            }
            titulo_mensaje = titulos_mensaje[canal]

            contenido += f"""## Lead {email_data['numero']}: {email_data['nombre']}

**Teléfono:** {email_data['telefono']}
{contacto_directo}**Email (verificar):** {email_data['email']}
**Canal recomendado:** {canal_label}
**Ubicación:** {email_data['direccion']}
**Google Maps:** [{email_data['nombre']}]({email_data['maps_url']})
**Estado Web:** NO TIENE
**Fuente:** Google Maps (datos verificados vía SerpAPI)

{titulo_mensaje}

{asunto_linea}{email_data['cuerpo']}

---

⚠️ **NOTAS ANTES DE ENVIAR:**
1. Si no hay WhatsApp ni email, verificar email llamando o revisando redes sociales del negocio
2. Confirmar teléfono llamando
3. Personalizar con datos adicionales si es posible
4. No enviar masivamente — máx 3-5 por día

---

"""

        contenido += f"""## Resumen

| Lead | Negocio | Teléfono | Canal recomendado | Estado |
|------|---------|----------|--------------------|--------|
"""

        canal_corto = {"whatsapp": "WhatsApp", "email": "Email", "telefono": "Solo teléfono"}
        for email_data in emails:
            contenido += f"| {email_data['numero']} | {email_data['nombre']} | {email_data['telefono']} | {canal_corto[email_data['canal_recomendado']]} | ✓ Listo |\n"

        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(contenido)


def main():
    """Punto de entrada"""
    cazador = CazadorLeads(base_dir=Path(__file__).parent)
    cazador.ejecutar()


if __name__ == "__main__":
    main()
