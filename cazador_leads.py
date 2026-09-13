#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cazador Leads Web — Prospección Automatizada de Negocios sin Página Web
Busca negocios reales en Google Maps (vía SerpAPI), filtra los que no tienen
página web y genera emails personalizados. No genera ni completa con datos
simulados/inventados bajo ninguna circunstancia.
"""

import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

try:
    import requests
except ImportError:
    print("⚠️  Instala las dependencias: pip install -r requirements.txt")
    exit(1)


class CazadorLeads:
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

        url = "https://nominatim.openstreetmap.org/search"
        headers = {"User-Agent": "CazadorLeadsWeb/1.0"}

        # Intenta primero con el texto limpio; si no encuentra nada y se había
        # modificado el texto, reintenta con el original (por si el nombre real
        # del lugar sí incluye esa palabra, ej. "Sector Los Andes").
        intentos = [ciudad_limpia]
        if ciudad_limpia != ciudad:
            intentos.append(ciudad)

        for intento in intentos:
            params = {"q": f"{intento}, {pais}", "format": "json", "limit": 1}
            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            resultados = response.json()

            if resultados:
                return {
                    "lat": float(resultados[0]["lat"]),
                    "lon": float(resultados[0]["lon"]),
                    "display_name": resultados[0]["display_name"]
                }

        return None

    def buscar_en_google(self):
        """Busca negocios REALES en Google Maps vía SerpAPI. No genera ni completa
        con datos simulados bajo ninguna circunstancia: si la búsqueda falla o no hay
        resultados, se retorna una lista vacía junto con self.error_busqueda explicando por qué."""
        self.error_busqueda = None
        query = self.nicho.strip()

        print(f"\n🔍 Buscando: '{query}' en {self.ciudad}, {self.pais}")

        serpapi_key = os.getenv("SERPAPI_KEY")
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

        # 2. Buscar en Google Maps real vía SerpAPI usando coordenadas
        try:
            url = "https://serpapi.com/search"
            params = {
                "engine": "google_maps",
                "q": query,
                "ll": f"@{geo['lat']},{geo['lon']},14z",
                "api_key": serpapi_key
            }

            print(f"   📡 Consultando Google Maps (SerpAPI)...")
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                self.error_busqueda = f"SerpAPI: {data['error']}"
                print(f"   ❌ {self.error_busqueda}")
                return []

            local_results = data.get("local_results", [])
            print(f"   📊 Negocios reales encontrados: {len(local_results)}")

            # Dominios que Google Maps a veces lista en el campo "website" pero que
            # NO son una página web propia (solo mensajería/redes) — un negocio con
            # únicamente uno de estos enlaces sigue siendo un lead válido (sin web).
            DOMINIOS_WHATSAPP = ("wa.me", "api.whatsapp.com", "whatsapp.com")
            DOMINIOS_REDES = ("m.me", "messenger.com", "facebook.com", "instagram.com", "linktr.ee")

            leads = []
            for place in local_results:
                nombre = place.get("title", "")
                if not nombre:
                    continue

                website = place.get("website", "") or ""
                website_lower = website.lower()

                es_whatsapp = bool(website) and any(d in website_lower for d in DOMINIOS_WHATSAPP)
                es_red_social = bool(website) and any(d in website_lower for d in DOMINIOS_REDES)
                es_web_propia = bool(website) and not es_whatsapp and not es_red_social

                place_id = place.get("place_id", "")
                maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else ""

                leads.append({
                    "nombre": nombre,
                    "telefono": place.get("phone", ""),
                    "whatsapp": website if es_whatsapp else None,
                    "redes_sociales": website if es_red_social else None,
                    "email": None,  # SerpAPI/Google Maps no expone emails; nunca se inventa
                    "direccion": place.get("address", ""),
                    "tiene_web": es_web_propia,
                    "url": website,
                    "maps_url": maps_url
                })

                if es_web_propia:
                    estado = "✓ CON WEB"
                elif es_whatsapp:
                    estado = "✗ SIN WEB (tiene WhatsApp)"
                elif es_red_social:
                    estado = "✗ SIN WEB (tiene red social)"
                else:
                    estado = "✗ SIN WEB"
                print(f"      {nombre}: {estado} ({website or 'sin sitio listado'})")

            if not leads:
                self.error_busqueda = "Google Maps no retornó negocios para esta búsqueda."

            return leads

        except requests.exceptions.RequestException as e:
            self.error_busqueda = f"Error de conexión con SerpAPI: {e}"
            print(f"   ❌ {self.error_busqueda}")
            return []
        except Exception as e:
            self.error_busqueda = f"Error inesperado: {e}"
            print(f"   ❌ {self.error_busqueda}")
            import traceback
            traceback.print_exc()
            return []

    def filtrar_sin_web(self, resultados):
        """Filtra solo negocios SIN página web - máximo self.max_results (config. vía MAX_RESULTS en .env)"""
        sin_web = [r for r in resultados if not r.get("tiene_web", True)]
        print(f"\n✓ Total encontrados: {len(resultados)}")
        print(f"✓ Con web: {len(resultados) - len(sin_web)}")
        print(f"✓ SIN web (leads): {len(sin_web)}")
        return sin_web[:self.max_results]

    def extraer_email_contacto(self, negocio):
        """Retorna el email SOLO si viene verificado desde la fuente real.
        Nunca se inventa ni se adivina un email — Google Maps no expone emails
        directamente, así que en la práctica esto será casi siempre None."""
        return negocio.get("email") or None

    def _telefono_a_whatsapp(self, telefono):
        """Construye un link wa.me a partir de un teléfono REAL verificado en Maps.
        No es un dato inventado (el teléfono ya es real) pero tampoco está
        confirmado que ese número use WhatsApp — por eso se marca aparte de un
        wa.me que el propio negocio publicó en su ficha."""
        if not telefono or telefono == "N/A":
            return None
        digitos = re.sub(r"\D", "", telefono)
        if len(digitos) < 8:  # muy corto para ser un número real completo
            return None
        return f"https://wa.me/{digitos}"

    def generar_mensaje_personalizado(self, lead, numero):
        """Genera un mensaje personalizado para el lead, adaptado al canal de
        contacto REAL disponible (Google Maps casi nunca expone email para
        negocios sin web propia):
          1. WhatsApp — si el negocio publicó un link wa.me/api.whatsapp.com,
             o si no lo publicó pero sí hay teléfono real (se construye el link
             wa.me a partir del número — WhatsApp abre igual con cualquier
             número, publicado o no; se marca como "no confirmado" para que
             se sepa que no viene directamente de la ficha de Maps)
          2. Email — si viniera verificado desde la fuente (excepcional)
          3. Teléfono — como único canal, solo si no hay ningún número utilizable
        Solo cita datos verificables (nombre, ubicación). No incluye casos de
        éxito ni estadísticas inventadas."""
        nombre = lead.get("nombre", "Negocio")
        telefono = lead.get("telefono") or "N/A"
        email = self.extraer_email_contacto(lead)

        whatsapp = lead.get("whatsapp")
        whatsapp_confirmado = bool(whatsapp)
        if not whatsapp:
            whatsapp = self._telefono_a_whatsapp(telefono)

        canal = "whatsapp" if whatsapp else ("email" if email else "telefono")

        # Datos de remitente: deben configurarse en .env. Si no están configurados,
        # se usan placeholders explícitos en vez de inventar una identidad o agencia.
        remitente_nombre = os.getenv("REMITENTE_NOMBRE") or "[TU NOMBRE]"
        remitente_cargo = os.getenv("REMITENTE_CARGO") or "[TU CARGO]"
        agencia_nombre = os.getenv("AGENCIA_NOMBRE") or "[TU AGENCIA]"
        remitente_contacto = os.getenv("REMITENTE_CONTACTO") or "[TU EMAIL / TELÉFONO]"

        asunto = None

        if canal == "whatsapp":
            cuerpo = f"""Hola! 👋

Vi que {nombre} aparece en Google Maps pero sin página web propia.

Cada mes hay personas que buscan en Google, no encuentran una web y terminan yendo con la competencia.

En {agencia_nombre} ayudamos a negocios como el tuyo a conseguir más clientes con desarrollo web.

¿Tienes 5 minutos esta semana para contarte cómo?

{remitente_nombre} — {agencia_nombre}
{remitente_contacto}"""
        else:
            asunto = f"{nombre}: sin web = clientes que pierden cada mes"
            cuerpo = f"""Hola,

vi que aparecen en Google Maps pero sin página web propia.

Cada mes hay personas que los buscan en Google, no encuentran una web y terminan en la competencia.

En {agencia_nombre} trabajamos con {self.nicho} ayudándoles a captar más clientes desde búsquedas de Google, a través de desarrollo web.

¿Tiene sentido explorar si aplica a vuestro caso?
¿Tienes 20 minutos esta semana?

{remitente_nombre}
{remitente_cargo} — {agencia_nombre}
{remitente_contacto}"""

        return {
            "numero": numero,
            "nombre": nombre,
            "telefono": telefono,
            "whatsapp": whatsapp,
            "whatsapp_confirmado": whatsapp_confirmado,
            "redes_sociales": lead.get("redes_sociales"),
            "email": email or "No disponible (Google Maps no lo publica — verificar manualmente)",
            "canal_recomendado": canal,
            "direccion": lead.get("direccion") or "N/A",
            "maps_url": lead.get("maps_url", ""),
            "asunto": asunto,
            "cuerpo": cuerpo
        }

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
        for i, lead in enumerate(self.leads, 1):
            email_data = self.generar_mensaje_personalizado(lead, i)
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
