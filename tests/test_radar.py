# -*- coding: utf-8 -*-
"""Pruebas offline (sin internet ni créditos de SerpAPI). Ejecutar: pytest tests"""
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_dir}/test.db"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "clave-de-prueba-123"
os.environ["SERPAPI_KEY"] = "clave-falsa"

import escaner  # noqa: E402
import mensajes  # noqa: E402

HTML_SIN_NADA = "<html><head><title>Clínica Sol</title></head><body><h1>Hola</h1>" + "<p>texto largo</p>" * 40 + "</body></html>"
HTML_BUENO = """<html><head><title>Clínica Sol en Pereira</title>
<meta name="viewport" content="width=device-width"><meta name="description" content="Clínica veterinaria en Pereira con urgencias 24 horas">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABCDEF1234"></script>
<script>fbq('init','123');</script>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"VeterinaryCare"}</script></head>
<body><h1>Sol</h1><a href="tel:+57300">Llamar</a><a href="https://wa.me/57300">WhatsApp</a>
<iframe src="https://www.google.com/maps/embed?pb=1"></iframe>""" + "<p>contenido</p>" * 40 + "</body></html>"


def escaneo_de(html, https=True, ms=800, ciudad="Pereira"):
    return dict(url="https://x.co", estado="ok", https=https, tiempo_ms=ms, **escaner.analizar_html(html, ciudad))


def neg(**kw):
    base = dict(nombre="Clínica Sol", telefono="+57 300 111 2233", whatsapp=None, redes_sociales=None, email=None,
                rating=4.6, resenas=120, horario="Abierto", nicho="clínicas veterinarias", ciudad="Pereira",
                clase_web="ninguna", url="", tipo="Veterinario", competidores_con_web=3)
    base.update(kw)
    return base


# ------------------------------------------------------------------ clasificación

@pytest.mark.parametrize("url,esperado", [
    ("", "ninguna"), ("https://wa.me/573001112233", "whatsapp"), ("https://www.facebook.com/x", "red"),
    ("https://instagram.com/x", "red"), ("https://wix.com", "propia"),  # 'x.com' no debe coincidir con wix.com
    ("https://miclinica.com", "propia"), ("https://www.paginasamarillas.com.co/x", "directorio"),
    ("https://clinica.business.site", "business_site"),
])
def test_clasificar_url(url, esperado):
    assert escaner.clasificar_url(url) == esperado


def test_url_segura_bloquea_redes_internas():
    for u in ("http://127.0.0.1/", "http://localhost:8080", "http://10.0.0.5/", "http://169.254.169.254/latest",
              "ftp://ejemplo.com", "file:///etc/passwd"):
        assert not escaner.url_segura(u), u


# ------------------------------------------------------------------ evaluación

def tipos(ev):
    return [o["tipo"] for o in ev["oportunidades"]]


def test_sin_web_buen_negocio_es_prioridad_alta():
    ev = escaner.evaluar(neg())
    assert tipos(ev)[0] == "sin_web"
    assert ev["prioridad"] == "alta" and ev["score"] >= 70
    assert ev["ticket"] == "alto"


def test_sin_web_poco_valioso_baja_de_prioridad():
    ev = escaner.evaluar(neg(rating=None, resenas=0, telefono="", nicho="restaurantes", competidores_con_web=0))
    assert ev["prioridad"] != "alta"


def test_web_sin_medicion_se_detecta():
    ev = escaner.evaluar(neg(clase_web="propia", url="https://x.co"), escaneo_de(HTML_SIN_NADA))
    assert "sin_medicion" in tipos(ev)
    assert "sin_web" not in tipos(ev)


def test_web_con_pixel_y_ga4_no_marca_medicion():
    ev = escaner.evaluar(neg(clase_web="propia", url="https://x.co"), escaneo_de(HTML_BUENO))
    assert "sin_medicion" not in tipos(ev)
    assert "web_mala" not in tipos(ev)
    assert "seo_local" not in tipos(ev)


def test_gtm_presente_no_se_afirma_que_falte_medicion():
    html = HTML_SIN_NADA.replace("</head>", '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-ABCD123"></script></head>')
    ev = escaner.evaluar(neg(clase_web="propia", url="https://x.co"), escaneo_de(html))
    assert "sin_medicion" not in tipos(ev)


def test_web_solo_js_no_afirma_nada_de_medicion():
    html = '<html><head><title>x</title></head><body><div id="root"></div></body></html>'
    ev = escaner.evaluar(neg(clase_web="propia", url="https://x.co"), escaneo_de(html))
    assert "sin_medicion" not in tipos(ev)


def test_web_sin_https_ni_movil_es_web_mala():
    ev = escaner.evaluar(neg(clase_web="propia", url="http://x.co"), escaneo_de(HTML_SIN_NADA, https=False))
    assert "web_mala" in tipos(ev)


def test_web_bloqueada_no_genera_falsos_positivos():
    esc = {"url": "https://x.co", "estado": "bloqueado", "detalle": "bloqueo"}
    ev = escaner.evaluar(neg(clase_web="propia", url="https://x.co"), esc)
    assert not ({"sin_medicion", "web_mala", "sin_captacion"} & set(tipos(ev)))


def test_web_caida_queda_como_no_verificada():
    esc = {"url": "https://x.co", "estado": "error", "detalle": "La web no responde (tiempo agotado)"}
    ev = escaner.evaluar(neg(clase_web="propia", url="https://x.co"), esc)
    opp = next(o for o in ev["oportunidades"] if o["tipo"] == "web_mala")
    assert opp["verificado"] is False


def test_gestion_es_siempre_hipotesis():
    ev = escaner.evaluar(neg())
    g = next(o for o in ev["oportunidades"] if o["tipo"] == "gestion")
    assert g["verificado"] is False and "Hipótesis" in g["detalle"]


def test_seo_local_requiere_dos_problemas():
    ev = escaner.evaluar(neg(resenas=8, horario="", rating=4.8))
    assert "seo_local" in tipos(ev)
    ev2 = escaner.evaluar(neg(resenas=8, horario="Abierto", rating=4.8))
    assert "seo_local" not in tipos(ev2)


def test_reputacion():
    assert "reputacion" in tipos(escaner.evaluar(neg(rating=3.6, resenas=40)))


# ------------------------------------------------------------------ mensajes

def lead_msg(ev, **kw):
    d = dict(nombre="Clínica Sol", nicho="clínicas veterinarias", ciudad="Pereira", rating=4.6, resenas=120,
             telefono="+57300", whatsapp="https://wa.me/57300", email=None, web_url="https://x.co",
             competidores_nombres=["Vet Uno", "Vet Dos"], clave="k1")
    d.update(oportunidades=ev["oportunidades"], diagnostico=ev["diagnostico"])
    d.update(kw)
    return d


def test_todos_los_mensajes_cumplen_las_reglas():
    os.environ["CASO_EXITO"] = "una clínica de Cali pasó de 4 a 15 citas por semana desde Google"
    evs = [escaner.evaluar(neg()),
           escaner.evaluar(neg(clase_web="propia", url="http://x.co"), escaneo_de(HTML_SIN_NADA, https=False)),
           escaner.evaluar(neg(rating=3.7, resenas=8, horario="")),
           escaner.evaluar(neg(clase_web="propia", url="https://x.co"),
                           escaneo_de(HTML_SIN_NADA.replace("<h1>", "<h1>").replace("tel:", ""), https=True))]
    vistos = 0
    for ev in evs:
        for ang in [o["tipo"] for o in ev["oportunidades"]]:
            for canal in ("whatsapp", "email"):
                for paso in (0, 1, 2):
                    for var in ("a", "b"):
                        m = mensajes.construir(lead_msg(ev), angulo=ang, canal=canal, paso=paso, variante=var)
                        t = m["cuerpo"]
                        assert m["palabras"] <= mensajes.MAX_PALABRAS, (ang, canal, paso, var, m["palabras"])
                        assert "Clínica Sol" in t or "x.co" in t or "Clínica Sol" in (m["asunto"] or "")
                        assert "vuestro" not in t.lower() and "increíble" not in t.lower()
                        if canal == "email" and paso == 0:
                            assert m["asunto"]
                        vistos += 1
    assert vistos > 100
    os.environ.pop("CASO_EXITO")


def test_caso_de_exito_solo_si_existe():
    ev = escaner.evaluar(neg())
    os.environ.pop("CASO_EXITO", None)
    assert "caso reciente" not in mensajes.construir(lead_msg(ev), canal="email")["cuerpo"].lower()
    os.environ["CASO_EXITO"] = "una clínica de Cali pasó de 4 a 15 citas"
    assert "caso reciente" in mensajes.construir(lead_msg(ev), canal="email")["cuerpo"].lower()
    os.environ.pop("CASO_EXITO")


def test_mensaje_usa_datos_reales_de_maps():
    ev = escaner.evaluar(neg())
    t = mensajes.construir(lead_msg(ev), angulo="sin_web", canal="whatsapp", variante="a")["cuerpo"]
    assert "4,6★ (120 reseñas)" in t and "Vet Uno y Vet Dos ya tienen web" in t


# ------------------------------------------------------------------ base de datos / API

def test_migracion_agrega_columnas_a_bd_antigua(tmp_path):
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, clave VARCHAR(255) NOT NULL UNIQUE, nombre VARCHAR(255) NOT NULL, "
                "estado VARCHAR(20) NOT NULL, creado_en DATETIME NOT NULL, actualizado_en DATETIME NOT NULL)")
    con.execute("CREATE TABLE contactos (id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL, estado VARCHAR(20) NOT NULL, fecha DATETIME NOT NULL)")
    con.execute("INSERT INTO leads VALUES (1,'tel:1','Viejo','contactado','2026-01-01','2026-01-01')")
    con.commit()
    con.close()
    import subprocess
    codigo = ("import os,sqlite3;os.environ['DATABASE_URL']='sqlite:///" + str(ruta).replace("\\", "/") +
              "';import db;db.init_db();c=sqlite3.connect(r'" + str(ruta) + "');"
              "cols=[r[1] for r in c.execute('PRAGMA table_info(leads)')];"
              "print('OK' if 'score' in cols and 'oportunidades' in cols else 'FALTAN');"
              "print(c.execute('select nombre from leads').fetchone()[0])")
    out = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True)
    assert "OK" in out.stdout and "Viejo" in out.stdout, out.stdout + out.stderr


@pytest.fixture(scope="module")
def cliente():
    import app as aplicacion
    c = aplicacion.app.test_client()
    r = c.post("/login", data={"usuario": "admin", "password": "clave-de-prueba-123"})
    assert r.status_code == 302
    return c


H = {"X-Requested-With": "fetch"}

NEGOCIOS_FALSOS = [
    {"nombre": "Vet Sin Web", "telefono": "+57 300 111 2233", "whatsapp": None, "redes_sociales": None, "email": None,
     "direccion": "Cra 1 #2-3", "clase_web": "ninguna", "tiene_web": False, "url": "", "maps_url": "https://maps/x",
     "rating": 4.7, "resenas": 150, "tipo": "Veterinario", "horario": "Abierto", "lat": 4.81, "lon": -75.69},
    {"nombre": "Vet Solo Facebook", "telefono": "", "whatsapp": None, "redes_sociales": "https://facebook.com/v",
     "email": None, "direccion": "Cl 5", "clase_web": "red", "tiene_web": False, "url": "https://facebook.com/v",
     "maps_url": "", "rating": 4.1, "resenas": 12, "tipo": "Veterinario", "horario": "", "lat": 4.82, "lon": -75.7},
    {"nombre": "Vet Con Web", "telefono": "+57 300 999 8877", "whatsapp": None, "redes_sociales": None, "email": None,
     "direccion": "Av 9", "clase_web": "propia", "tiene_web": True, "url": "https://vetconweb.co", "maps_url": "",
     "rating": 4.8, "resenas": 300, "tipo": "Veterinario", "horario": "Abierto", "lat": 4.8, "lon": -75.68},
]


def esperar(cliente, job_id):
    for _ in range(100):
        d = cliente.get(f"/api/radar/{job_id}").get_json()
        if d["estado"] != "ejecutando":
            return d
        time.sleep(0.1)
    raise AssertionError("el radar no terminó")


def test_flujo_completo_radar(cliente, monkeypatch):
    import radar
    from cazador_leads import CazadorLeads

    def falso(self, paginas=None, puntos=1, cache=None, progreso=None):
        self.geo = {"lat": 4.81, "lon": -75.69, "display_name": "Pereira"}
        self.creditos_usados = 2
        return [dict(n) for n in NEGOCIOS_FALSOS]

    monkeypatch.setattr(CazadorLeads, "buscar_en_google", falso)
    monkeypatch.setattr(escaner, "escanear_web", lambda url, ciudad="": escaneo_de(HTML_SIN_NADA))

    # CSRF: sin cabecera se rechaza
    assert cliente.post("/api/radar", json={"ciudad": "Pereira"}).status_code == 403
    # validación
    assert cliente.post("/api/radar", json={"ciudad": "Pereira"}, headers=H).status_code == 400

    r = cliente.post("/api/radar", headers=H, json={"ciudad": "Pereira", "pais": "Colombia",
                                                    "sectores": ["veterinarias"], "cobertura": "normal"})
    assert r.status_code == 202 and r.get_json()["creditos_estimados"] == 2
    d = esperar(cliente, r.get_json()["job_id"])
    assert d["estado"] == "listo", d
    res = d["resultado"]
    assert res["total_negocios"] == 3 and res["creditos_usados"] == 2 and res["nuevos"] == 3
    scores = [l["score"] for l in res["leads"]]
    assert scores == sorted(scores, reverse=True)  # ordenado por score
    sin_web = next(l for l in res["leads"] if l["nombre"] == "Vet Sin Web")
    assert sin_web["prioridad"] == "alta"
    con_web = next(l for l in res["leads"] if l["nombre"] == "Vet Con Web")
    assert "sin_medicion" in [o["tipo"] for o in con_web["oportunidades"]]

    # repetir la búsqueda no duplica leads
    r2 = cliente.post("/api/radar", headers=H, json={"ciudad": "Pereira", "pais": "Colombia", "sectores": ["veterinarias"]})
    d2 = esperar(cliente, r2.get_json()["job_id"])
    assert d2["resultado"]["nuevos"] == 0
    assert len(cliente.get("/api/leads").get_json()["leads"]) == 3

    # filtros
    assert len(cliente.get("/api/leads?prioridad=alta").get_json()["leads"]) >= 1
    assert all("sin_web" in [o["tipo"] for o in l["oportunidades"]]
               for l in cliente.get("/api/leads?oportunidad=sin_web").get_json()["leads"])

    # mensaje bajo demanda + secuencia
    lid = sin_web["id"]
    m0 = cliente.get(f"/api/leads/{lid}/mensaje").get_json()
    assert m0["paso"] == 0 and m0["palabras"] <= 150 and "4,7★ (150 reseñas)" in m0["cuerpo"]
    t = cliente.post(f"/api/leads/{lid}/toque", headers=H, json={"canal": "whatsapp", "plantilla": m0["plantilla"]})
    assert t.status_code == 200 and t.get_json()["estado"] == "contactado"
    assert t.get_json()["proximo_seguimiento"]  # +3 días
    m1 = cliente.get(f"/api/leads/{lid}/mensaje").get_json()
    assert m1["paso"] == 1
    assert cliente.post(f"/api/leads/{lid}/toque", headers=H, json={"canal": "xx"}).status_code == 400

    a = cliente.get("/api/analitica").get_json()
    assert a["totales"]["leads"] == 3 and any(p["nombre"] == m0["plantilla"] for p in a["por_plantilla"])
    assert any(o["nombre"] == "Sin página web" for o in a["por_oportunidad"])
    assert cliente.get("/api/leads.csv").status_code == 200


def test_radar_reporta_error_de_busqueda(cliente, monkeypatch):
    from cazador_leads import CazadorLeads

    def vacio(self, **kw):
        self.error_busqueda = "SERPAPI_KEY no configurada en .env"
        return []

    monkeypatch.setattr(CazadorLeads, "buscar_en_google", vacio)
    r = cliente.post("/api/radar", headers=H, json={"ciudad": "X", "pais": "Y", "sectores": ["a"]})
    d = esperar(cliente, r.get_json()["job_id"])
    assert d["estado"] == "error" and "SERPAPI_KEY" in d["error"]


def test_mismo_negocio_en_dos_sectores_no_se_duplica(cliente, monkeypatch):
    from cazador_leads import CazadorLeads

    def falso(self, paginas=None, puntos=1, cache=None, progreso=None):
        self.geo = {"lat": 1.0, "lon": 1.0, "display_name": "X"}
        self.creditos_usados = 1
        return [dict(NEGOCIOS_FALSOS[0], nombre="Negocio Compartido", telefono="+57 311 000 9999")]

    monkeypatch.setattr(CazadorLeads, "buscar_en_google", falso)
    r = cliente.post("/api/radar", headers=H, json={"ciudad": "Cali", "pais": "Colombia",
                                                    "sectores": ["clínicas", "veterinarias"]})
    d = esperar(cliente, r.get_json()["job_id"])
    assert d["estado"] == "listo", d
    assert [l["nombre"] for l in d["resultado"]["leads"]] == ["Negocio Compartido"]
    assert d["resultado"]["nuevos"] == 1


# ------------------------------------------------------------------ email y WhatsApp desde la web

def _cf(email, k=0x42):
    return f"{k:02x}" + "".join(f"{ord(c) ^ k:02x}" for c in email)


HTML_CONTACTOS = f"""<html><body>
<a href="mailto:Ventas@MiClinica.com?subject=Hola">Escríbenos</a>
<a href="https://wa.me/573001112233?text=hola">WhatsApp</a>
<p>Atención: citas [at] miclinica [dot] com</p>
<span class="__cf_email__" data-cfemail="{_cf('gerencia@miclinica.com')}">[email&#160;protected]</span>
<img src="logo@2x.png"><p>plantilla: tuemail@tudominio.com y user@example.com y abc@sentry.io</p>
<script>var x = "oculto@scripts.com";</script>
</body></html>"""


def test_extrae_emails_y_whatsapp_publicados():
    emails, was = escaner.extraer_contactos_html(HTML_CONTACTOS, "https://miclinica.com/")
    valores = {e["valor"] for e in emails}
    assert {"ventas@miclinica.com", "citas@miclinica.com", "gerencia@miclinica.com"} <= valores
    # basura descartada: imágenes, plantillas, ejemplos, sentry y contenido de <script>
    assert not any(b in v for v in valores for b in ("2x.png", "tudominio", "example", "sentry", "scripts.com"))
    assert [w["numero"] for w in was] == ["573001112233"] and was[0]["link"] == "https://wa.me/573001112233"


def test_orden_prefiere_email_del_dominio_de_la_web():
    html = '<a href="mailto:ventas@miclinica.com">x</a> <p>gmail: alguien@gmail.com</p>'
    emails, _ = escaner.extraer_contactos_html(html, "https://miclinica.com/")
    ordenados = escaner._ordenar_emails(emails + [{"valor": "otro@gmail.com", "fuente": "https://miclinica.com/", "via": "texto"}],
                                        "https://miclinica.com/")
    assert ordenados[0]["valor"] == "ventas@miclinica.com"


def test_enlaces_de_contacto_y_aviso_legal_solo_del_mismo_dominio():
    html = ('<a href="/aviso-legal">Aviso legal</a><a href="/contacto">Contacto</a>'
            '<a href="https://otrositio.com/contacto">Ajeno</a><a href="/productos">Productos</a>')
    enlaces = escaner._enlaces_contacto(html, "https://miclinica.com/")
    assert enlaces == ["https://miclinica.com/aviso-legal", "https://miclinica.com/contacto"]


def test_busca_el_email_en_el_aviso_legal(monkeypatch):
    portada = '<html><body><a href="/aviso-legal">Aviso legal</a><p>Sin datos de contacto</p></body></html>'
    legal = "<html><body><p>Titular: Clínica SL. Email de contacto: legal@miclinica.com</p></body></html>"
    pedidas = []

    def falso(url, timeout=(5, 9)):
        pedidas.append(url)
        return {"estado": "ok", "html": legal, "url_final": url}

    monkeypatch.setattr(escaner, "descargar", falso)
    c = escaner.buscar_contactos(portada, "https://miclinica.com/")
    assert pedidas == ["https://miclinica.com/aviso-legal"]
    assert c["emails"][0]["valor"] == "legal@miclinica.com"
    assert c["emails"][0]["fuente"].endswith("/aviso-legal")


def test_no_descarga_mas_paginas_si_ya_tiene_email_y_whatsapp(monkeypatch):
    monkeypatch.setattr(escaner, "descargar", lambda *a, **k: pytest.fail("no debía descargar"))
    c = escaner.buscar_contactos(HTML_CONTACTOS + '<a href="/aviso-legal">Aviso legal</a>', "https://miclinica.com/")
    assert c["emails"] and c["whatsapps"]


def test_sin_datos_publicados_no_se_inventa_nada(monkeypatch):
    monkeypatch.setattr(escaner, "descargar", lambda *a, **k: {"estado": "error"})
    c = escaner.buscar_contactos("<html><body>Hola <a href='/contacto'>Contacto</a></body></html>", "https://x.co/")
    assert c == {"emails": [], "whatsapps": []}


def test_lead_usa_email_y_whatsapp_de_la_web_y_recomienda_email_si_no_hay_whatsapp_confirmado():
    from cazador_leads import CazadorLeads
    cz = CazadorLeads()
    cz.nicho, cz.ciudad, cz.pais = "clínicas veterinarias", "Pereira", "Colombia"
    base = dict(NEGOCIOS_FALSOS[2], telefono="+57 300 999 8877")
    # 1) la web publica email pero no WhatsApp -> canal email (el WhatsApp derivado del teléfono no está confirmado)
    esc = escaneo_de(HTML_SIN_NADA)
    esc["contactos"] = {"emails": [{"valor": "info@vetconweb.co", "fuente": "https://vetconweb.co/aviso-legal", "via": "texto"}],
                        "whatsapps": []}
    lead = cz.preparar_lead(base, 1, escaneo=esc)
    assert lead["email_real"] == "info@vetconweb.co"
    assert lead["whatsapp_confirmado"] is False and lead["canal_recomendado"] == "email"
    assert lead["asunto"] and lead["diagnostico"]["contactos"]["emails"][0]["valor"] == "info@vetconweb.co"
    # 2) la web publica WhatsApp -> canal whatsapp confirmado
    esc2 = escaneo_de(HTML_SIN_NADA)
    esc2["contactos"] = {"emails": [], "whatsapps": [{"numero": "573009998877", "link": "https://wa.me/573009998877", "fuente": "https://vetconweb.co/"}]}
    lead2 = cz.preparar_lead(base, 1, escaneo=esc2)
    assert lead2["whatsapp"] == "https://wa.me/573009998877" and lead2["whatsapp_confirmado"] is True
    assert lead2["canal_recomendado"] == "whatsapp"
    # 3) sin nada publicado: no hay email inventado
    lead3 = cz.preparar_lead(base, 1, escaneo=escaneo_de(HTML_SIN_NADA))
    assert lead3["email_real"] is None


def test_radar_guarda_email_encontrado_en_la_web(cliente, monkeypatch):
    from cazador_leads import CazadorLeads

    def falso(self, paginas=None, puntos=1, cache=None, progreso=None):
        self.geo = {"lat": 2.0, "lon": 2.0, "display_name": "X"}
        self.creditos_usados = 1
        return [dict(NEGOCIOS_FALSOS[2], nombre="Vet Contacto Web", telefono="+57 312 222 3344", url="https://vetcontacto.co")]

    def escaneo(url, ciudad=""):
        e = escaneo_de(HTML_SIN_NADA)
        e["contactos"] = {"emails": [{"valor": "info@vetcontacto.co", "fuente": "https://vetcontacto.co/aviso-legal", "via": "texto"}],
                          "whatsapps": []}
        return e

    monkeypatch.setattr(CazadorLeads, "buscar_en_google", falso)
    monkeypatch.setattr(escaner, "escanear_web", escaneo)
    r = cliente.post("/api/radar", headers=H, json={"ciudad": "Armenia", "pais": "Colombia", "sectores": ["veterinarias"]})
    d = esperar(cliente, r.get_json()["job_id"])
    assert d["estado"] == "listo", d
    lead = d["resultado"]["leads"][0]
    assert lead["email"] == "info@vetcontacto.co"
    assert lead["diagnostico"]["contactos"]["emails"][0]["fuente"].endswith("/aviso-legal")
    assert cliente.get(f"/api/leads/{lead['id']}/mensaje").get_json()["canal"] == "email"


# ------------------------------------------------------------------ Instagram / Facebook y mapa

import redes  # noqa: E402


def test_es_perfil_red():
    assert redes.es_perfil_red("https://www.instagram.com/vetcorales/")
    assert redes.es_perfil_red("https://m.facebook.com/vetcorales")
    assert not redes.es_perfil_red("https://linktr.ee/vetcorales")
    assert not redes.es_perfil_red("https://instagram.com.malo.co/x")


def test_extrae_contactos_de_una_bio():
    bio = ("1.2K Followers, 300 Following - Vet Corales. Citas: +57 310 555 1002 · info@vetcorales.co · "
           "escríbenos wa.me/573105551002 · desde 2019 2020 2021")
    c = redes.extraer_de_texto(bio, "https://instagram.com/vetcorales")
    assert [e["valor"] for e in c["emails"]] == ["info@vetcorales.co"]
    assert [w["numero"] for w in c["whatsapps"]] == ["573105551002"]
    assert [t["digitos"] for t in c["telefonos"]] == ["573105551002"]  # los años y los seguidores no cuentan
    assert redes.extraer_de_texto("96.203 seguidores · 766 personas hablan de esto", "x")["telefonos"] == []


def test_leer_perfil_usa_la_bio_publica(monkeypatch):
    html = '<html><head><meta property="og:description" content="Vet Corales. Citas al 300 111 2233 - hola@vetcorales.co"></head></html>'
    monkeypatch.setattr(escaner, "descargar", lambda u, timeout=None: {"estado": "ok", "html": html, "url_final": u})
    r = redes.leer_perfil("https://www.facebook.com/vetcorales")
    assert r["estado"] == "ok" and r["contactos"]["emails"][0]["valor"] == "hola@vetcorales.co"
    assert redes.leer_perfil("https://miweb.com")["estado"] == "no_aplica"


def test_perfil_con_muro_de_login_no_inventa_nada(monkeypatch):
    html = '<html><head><meta property="og:description" content="Inicia sesión o regístrate para verlo"></head></html>'
    monkeypatch.setattr(escaner, "descargar", lambda u, timeout=None: {"estado": "ok", "html": html, "url_final": u})
    c = redes.leer_perfil("https://m.facebook.com/x")["contactos"]
    assert c == {"emails": [], "whatsapps": [], "telefonos": []}


def test_coincidencia_evita_homonimos():
    assert redes.coincide("Clínica Veterinaria Patitas", "Patitas Vet (@patitasvet) · Pereira")
    assert not redes.coincide("Clínica Veterinaria Patitas", "Mascotas Felices - Cali")
    assert redes.coincide("Vet Corales", "Vet Corales | Facebook")


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def test_buscar_perfiles_filtra_homonimos_y_usa_cache(monkeypatch):
    os.environ["SERPAPI_KEY"] = "clave-falsa"
    llamadas = []
    data = {"organic_results": [
        {"link": "https://www.instagram.com/patitasvet/", "title": "Patitas Vet (@patitasvet)",
         "snippet": "300 Followers - Veterinaria en Pereira. Citas: +57 311 222 3344. patitas@gmail.com"},
        {"link": "https://www.facebook.com/otraclinica", "title": "Otra Clínica", "snippet": "tel: 300 999 0000 otra@x.co"},
        {"link": "https://www.patitas.com", "title": "Patitas Vet", "snippet": "web propia, no es una red"},
    ]}
    monkeypatch.setattr(redes.requests, "get", lambda *a, **k: (llamadas.append(k), _Resp(data))[1])

    class Cache(dict):
        def set(self, k, v):
            self[k] = v

    cache = Cache()
    r = redes.buscar_perfiles("Clínica Patitas Vet", "Pereira", cache=cache)
    assert r["creditos"] == 1 and len(llamadas) == 1
    assert [p["red"] for p in r["perfiles"]] == ["instagram"]
    assert [e["valor"] for e in r["emails"]] == ["patitas@gmail.com"]
    assert r["telefonos"][0]["digitos"] == "573112223344"
    r2 = redes.buscar_perfiles("Clínica Patitas Vet", "Pereira", cache=cache)  # misma consulta: caché
    assert r2["creditos"] == 0 and len(llamadas) == 1 and r2["emails"] == r["emails"]


def test_buscar_perfiles_sin_clave():
    os.environ["SERPAPI_KEY"] = "tu_api_key_aqui"
    with pytest.raises(redes.RedesError):
        redes.buscar_perfiles("X", "Y")
    os.environ["SERPAPI_KEY"] = "clave-falsa"


def test_api_buscar_redes_actualiza_el_lead(cliente, monkeypatch):
    from cazador_leads import CazadorLeads

    def falso(self, paginas=None, puntos=1, cache=None, progreso=None):
        self.geo = {"lat": 3.0, "lon": 3.0, "display_name": "X"}
        self.creditos_usados = 1
        return [dict(NEGOCIOS_FALSOS[0], nombre="Mascotas Felices Pasto", telefono="")]

    monkeypatch.setattr(CazadorLeads, "buscar_en_google", falso)
    r = cliente.post("/api/radar", headers=H, json={"ciudad": "Pasto", "pais": "Colombia", "sectores": ["veterinarias"]})
    d = esperar(cliente, r.get_json()["job_id"])
    lead = d["resultado"]["leads"][0]
    assert not lead["email"] and not lead["telefono"] and lead["canal_recomendado"] != "email"

    resultado = {"perfiles": [{"url": "https://www.instagram.com/mascotasfelicespasto/", "red": "instagram", "titulo": "t", "snippet": "s"}],
                 "emails": [{"valor": "hola@mascotasfelices.co", "fuente": "https://www.instagram.com/mascotasfelicespasto/", "via": "bio pública (Google)"}],
                 "whatsapps": [], "telefonos": [{"numero": "+57 320 111 2222", "digitos": "573201112222", "fuente": "x"}], "creditos": 1}
    monkeypatch.setattr(redes, "buscar_perfiles", lambda nombre, ciudad, cache=None: resultado)
    assert cliente.post(f"/api/leads/{lead['id']}/redes").status_code == 403  # CSRF
    out = cliente.post(f"/api/leads/{lead['id']}/redes", headers=H).get_json()
    assert out["email"] == "hola@mascotasfelices.co"
    assert out["redes_sociales"].endswith("/mascotasfelicespasto/")
    assert out["telefono"] == "+57 320 111 2222"
    assert out["diagnostico"]["redes"]["creditos"] == 1
    assert out["diagnostico"]["contactos"]["emails"][0]["valor"] == "hola@mascotasfelices.co"
    assert cliente.get(f"/api/leads/{lead['id']}/mensaje").get_json()["canal"] == "email"
    # una nueva consulta no pisa un email ya guardado
    resultado["emails"] = [{"valor": "otro@x.co", "fuente": "u", "via": "v"}]
    assert cliente.post(f"/api/leads/{lead['id']}/redes", headers=H).get_json()["email"] == "hola@mascotasfelices.co"


def test_api_buscar_redes_error_de_serpapi(cliente, monkeypatch):
    lid = cliente.get("/api/leads").get_json()["leads"][0]["id"]

    def falla(*a, **k):
        raise redes.RedesError("SERPAPI_KEY no configurada en .env")

    monkeypatch.setattr(redes, "buscar_perfiles", falla)
    r = cliente.post(f"/api/leads/{lid}/redes", headers=H)
    assert r.status_code == 502 and "SERPAPI_KEY" in r.get_json()["error"]


def test_radar_lee_el_perfil_publicado_en_maps(cliente, monkeypatch):
    from cazador_leads import CazadorLeads

    def falso(self, paginas=None, puntos=1, cache=None, progreso=None):
        self.geo = {"lat": 3.0, "lon": 3.0, "display_name": "X"}
        self.creditos_usados = 1
        return [dict(NEGOCIOS_FALSOS[1], nombre="Vet Perfil FB", telefono="+57 301 777 8899",
                     url="https://www.facebook.com/vetperfil", redes_sociales="https://www.facebook.com/vetperfil")]

    html = '<html><head><meta property="og:description" content="Vet Perfil. Escríbenos: contacto@vetperfil.co"></head></html>'
    monkeypatch.setattr(CazadorLeads, "buscar_en_google", falso)
    monkeypatch.setattr(escaner, "descargar", lambda u, timeout=None: {"estado": "ok", "html": html, "url_final": u})
    r = cliente.post("/api/radar", headers=H, json={"ciudad": "Ipiales", "pais": "Colombia", "sectores": ["veterinarias"]})
    d = esperar(cliente, r.get_json()["job_id"])
    lead = d["resultado"]["leads"][0]
    assert lead["email"] == "contacto@vetperfil.co" and lead["diagnostico"]["red_social"]["estado"] == "ok"


def test_geocodificar_para_mover_el_mapa(cliente, monkeypatch):
    from cazador_leads import CazadorLeads
    monkeypatch.setattr(CazadorLeads, "geocodificar",
                        lambda self, c, p: {"lat": 37.18, "lon": -3.6, "display_name": "Granada, España"} if c == "Granada" else None)
    ok = cliente.get("/api/geocodificar?ciudad=Granada&pais=España")
    assert ok.status_code == 200 and ok.get_json()["lat"] == 37.18
    assert cliente.get("/api/geocodificar?ciudad=Nadaland&pais=X").status_code == 404
    assert cliente.get("/api/geocodificar?ciudad=Granada").status_code == 400


# ------------------------------------------------------------------ lote de redes (sin IA)

def _sembrar_leads_para_lote(cliente, monkeypatch, ciudad, nombres):
    from cazador_leads import CazadorLeads

    def falso(self, paginas=None, puntos=1, cache=None, progreso=None):
        self.geo = {"lat": 5.0, "lon": 5.0, "display_name": "X"}
        self.creditos_usados = 1
        out = []
        for i, n in enumerate(nombres):
            out.append(dict(NEGOCIOS_FALSOS[0], nombre=n, telefono=f"+57 315 {sum(map(ord, ciudad)):04d} 10{i:02d}",
                            rating=4.9 - i * 0.3, resenas=300 - i * 80))
        return out

    monkeypatch.setattr(CazadorLeads, "buscar_en_google", falso)
    r = cliente.post("/api/radar", headers=H, json={"ciudad": ciudad, "pais": "Colombia", "sectores": ["odontólogos"]})
    d = esperar(cliente, r.get_json()["job_id"])
    assert d["estado"] == "listo", d
    return {l["nombre"]: l["id"] for l in d["resultado"]["leads"]}


def _esperar_lote(cliente, job_id):
    for _ in range(100):
        d = cliente.get(f"/api/redes/lote/{job_id}").get_json()
        if d["estado"] != "ejecutando":
            return d
        time.sleep(0.1)
    raise AssertionError("el lote no terminó")


def test_lote_respeta_el_tope_de_creditos_y_el_orden_por_puntuacion(cliente, monkeypatch):
    ids = _sembrar_leads_para_lote(cliente, monkeypatch, "Tunja", ["Dental Uno", "Dental Dos", "Dental Tres", "Dental Cuatro"])
    import db
    from sqlalchemy import update as _upd
    with db.engine.begin() as conn:  # aísla el test: solo estos 4 leads son candidatos
        conn.execute(_upd(db.leads).where(~db.leads.c.id.in_(list(ids.values()))).values(estado="descartado"))
    consultados = []

    def falso(nombre, ciudad, cache=None):
        consultados.append(nombre)
        con_datos = nombre == "Dental Uno"
        return {"perfiles": [{"url": "https://www.instagram.com/dentaluno/", "red": "instagram", "titulo": "t", "snippet": "s"}] if con_datos else [],
                "emails": [{"valor": "hola@dentaluno.co", "fuente": "https://www.instagram.com/dentaluno/", "via": "v"}] if con_datos else [],
                "whatsapps": [], "telefonos": [], "creditos": 1}

    monkeypatch.setattr(redes, "buscar_perfiles", falso)
    # sin CSRF / sin tope / tope inválido
    assert cliente.post("/api/redes/lote", json={"max_creditos": 2}).status_code == 403
    assert cliente.post("/api/redes/lote", headers=H, json={}).status_code == 400
    assert cliente.post("/api/redes/lote", headers=H, json={"max_creditos": 0}).status_code == 400

    cand = cliente.get("/api/redes/lote/candidatos").get_json()
    assert cand["candidatos"] >= 4
    r = cliente.post("/api/redes/lote", headers=H, json={"max_creditos": 2})
    assert r.status_code == 202
    d = _esperar_lote(cliente, r.get_json()["job_id"])
    assert d["estado"] == "listo", d
    res = d["resultado"]
    assert res["creditos_usados"] == 2 and res["procesados"] == 2  # se detuvo en el tope
    assert res["con_email"] == 1 and res["sin_datos"] == 1 and res["detenido_por_tope"] is True
    assert consultados[0] == "Dental Uno"  # el de mayor puntuación primero
    lead = cliente.get(f"/api/leads/{ids['Dental Uno']}").get_json()
    assert lead["email"] == "hola@dentaluno.co" and lead["diagnostico"]["redes"]["creditos"] == 1
    assert "Dental Cuatro" not in consultados

    # los ya consultados no se repiten en el siguiente lote
    consultados.clear()
    r2 = cliente.post("/api/redes/lote", headers=H, json={"max_creditos": 50})
    d2 = _esperar_lote(cliente, r2.get_json()["job_id"])
    assert "Dental Uno" not in consultados and "Dental Dos" not in consultados
    assert d2["resultado"]["detenido_por_tope"] is False


def test_lote_las_consultas_en_cache_no_gastan_credito(cliente, monkeypatch):
    _sembrar_leads_para_lote(cliente, monkeypatch, "Duitama", ["Ortodoncia Sol", "Ortodoncia Luna"])
    monkeypatch.setattr(redes, "buscar_perfiles", lambda n, c, cache=None: {
        "perfiles": [], "emails": [], "whatsapps": [], "telefonos": [], "creditos": 0})
    r = cliente.post("/api/redes/lote", headers=H, json={"max_creditos": 1})
    d = _esperar_lote(cliente, r.get_json()["job_id"])
    assert d["estado"] == "listo" and d["resultado"]["creditos_usados"] == 0
    assert d["resultado"]["procesados"] >= 2  # con caché pasa de largo el tope de 1 crédito


def test_lote_se_detiene_tras_errores_seguidos_y_sin_clave(cliente, monkeypatch):
    _sembrar_leads_para_lote(cliente, monkeypatch, "Sogamoso", ["Consultorio A", "Consultorio B", "Consultorio C", "Consultorio D"])

    def falla(n, c, cache=None):
        raise redes.RedesError("Error de conexión con SerpAPI: timeout")

    monkeypatch.setattr(redes, "buscar_perfiles", falla)
    r = cliente.post("/api/redes/lote", headers=H, json={"max_creditos": 10})
    d = _esperar_lote(cliente, r.get_json()["job_id"])
    assert d["estado"] == "error" and "3 errores seguidos" in d["error"]

    monkeypatch.setenv("SERPAPI_KEY", "tu_api_key_aqui")
    assert cliente.post("/api/redes/lote", headers=H, json={"max_creditos": 5}).status_code == 400
    monkeypatch.setenv("SERPAPI_KEY", "clave-falsa")


def test_lote_sin_candidatos(cliente, monkeypatch):
    monkeypatch.setattr(redes, "buscar_perfiles", lambda n, c, cache=None: {
        "perfiles": [], "emails": [], "whatsapps": [], "telefonos": [], "creditos": 0})
    for _ in range(3):  # vacía la cola de candidatos
        r = cliente.post("/api/redes/lote", headers=H, json={"max_creditos": 50})
        if r.status_code != 202:
            break
        _esperar_lote(cliente, r.get_json()["job_id"])
    r = cliente.post("/api/redes/lote", headers=H, json={"max_creditos": 5})
    assert r.status_code == 400 and "No hay leads" in r.get_json()["error"]
    assert cliente.get("/api/redes/lote/noexiste").status_code == 404


# ------------------------------------------------------------------ consumo de créditos y datos del panel

def test_ocultar_clave_en_errores():
    msg = "HTTPSConnectionPool(host='serpapi.com'): Max retries exceeded with url: /search?engine=google&q=x&api_key=SECRETA123&num=6 (Caused by X)"
    limpio = escaner.ocultar_clave(msg)
    assert "SECRETA123" not in limpio and "api_key=***" in limpio and "num=6" in limpio


def test_error_de_conexion_no_filtra_la_clave(monkeypatch):
    os.environ["SERPAPI_KEY"] = "CLAVE-SECRETA-XYZ"

    def falla(*a, **k):
        raise redes.requests.ConnectionError("Max retries exceeded with url: /search?q=x&api_key=CLAVE-SECRETA-XYZ")

    monkeypatch.setattr(redes.requests, "get", falla)
    with pytest.raises(redes.RedesError) as e:
        redes.buscar_perfiles("Vet X", "Cali")
    assert "CLAVE-SECRETA-XYZ" not in str(e.value)
    os.environ["SERPAPI_KEY"] = "clave-falsa"


def test_radar_registra_creditos_y_ahorro_por_cache(cliente, monkeypatch):
    import db
    from cazador_leads import CazadorLeads
    from sqlalchemy import select as _sel

    def falso(self, paginas=None, puntos=1, cache=None, progreso=None):
        self.geo = {"lat": 6.0, "lon": 6.0, "display_name": "X"}
        self.creditos_usados = 2
        self.consultas_cache = 3
        return [dict(NEGOCIOS_FALSOS[0], nombre="Negocio Consumo", telefono="+57 316 555 0001")]

    monkeypatch.setattr(CazadorLeads, "buscar_en_google", falso)
    r = cliente.post("/api/radar", headers=H, json={"ciudad": "Neiva", "pais": "Colombia", "sectores": ["abogados"], "cobertura": "rapida"})
    assert esperar(cliente, r.get_json()["job_id"])["estado"] == "listo"
    with db.engine.connect() as conn:
        filas = conn.execute(_sel(db.consumo).where(db.consumo.c.ciudad == "Neiva")).mappings().all()
    assert len(filas) == 1
    f = filas[0]
    assert (f["tipo"], f["creditos"], f["ahorrados"], f["sector"]) == ("radar", 2, 3, "abogados") and f["usuario_id"]


def test_registrar_consumo_ignora_cero_y_nunca_rompe(monkeypatch):
    import db
    from sqlalchemy import select as _sel, func as _f
    with db.engine.connect() as conn:
        antes = conn.execute(_sel(_f.count()).select_from(db.consumo)).scalar()
    db.registrar_consumo("radar", 0, 0)
    with db.engine.connect() as conn:
        assert conn.execute(_sel(_f.count()).select_from(db.consumo)).scalar() == antes
    monkeypatch.setattr(db.engine, "begin", lambda: (_ for _ in ()).throw(RuntimeError("bd caída")))
    db.registrar_consumo("radar", 5, 0)  # no lanza


def test_lead_a_lead_registra_consumo_de_redes(cliente, monkeypatch):
    import db
    from sqlalchemy import select as _sel
    lid = cliente.get("/api/leads").get_json()["leads"][0]["id"]
    monkeypatch.setattr(redes, "buscar_perfiles", lambda n, c, cache=None: {
        "perfiles": [], "emails": [], "whatsapps": [], "telefonos": [], "creditos": 1})
    assert cliente.post(f"/api/leads/{lid}/redes", headers=H).status_code == 200
    monkeypatch.setattr(redes, "buscar_perfiles", lambda n, c, cache=None: {
        "perfiles": [], "emails": [], "whatsapps": [], "telefonos": [], "creditos": 0})
    assert cliente.post(f"/api/leads/{lid}/redes", headers=H).status_code == 200
    with db.engine.connect() as conn:
        filas = conn.execute(_sel(db.consumo).where(db.consumo.c.lead_id == lid).order_by(db.consumo.c.id)).mappings().all()
    assert [(f["tipo"], f["creditos"], f["ahorrados"]) for f in filas] == [("redes", 1, 0), ("redes", 0, 1)]


def test_datos_del_panel(cliente):
    d = cliente.get("/api/analitica/datos").get_json()
    assert d["config"]["cuota_mes"] >= 1 and len(d["config"]["hoy"]) == 10
    assert d["leads"] and d["consumo"] and d["eventos"]
    l = d["leads"][0]
    for k in ("id", "creado", "estado", "usuario", "sector", "ciudad", "prioridad", "score", "oportunidades", "plantilla"):
        assert k in l
    assert isinstance(l["oportunidades"], list) and "0" in d["usuarios"]
    assert {c["tipo"] for c in d["consumo"]} <= {"radar", "redes"}
    assert cliente.get("/api/analitica/datos").status_code == 200


def test_cuenta_serpapi_no_filtra_la_clave_y_se_cachea(cliente, monkeypatch):
    import app as aplicacion
    os.environ["SERPAPI_KEY"] = "CLAVE-SECRETA-XYZ"
    aplicacion._cuenta.update(t=0.0, d=None)
    llamadas = []

    class R:
        def raise_for_status(self): pass
        def json(self): return {"plan_name": "Free", "searches_per_month": 100, "this_month_usage": 37, "total_searches_left": 63}

    monkeypatch.setattr(aplicacion.requests, "get", lambda *a, **k: (llamadas.append(1), R())[1])
    d = cliente.get("/api/serpapi/cuenta").get_json()
    assert d == {"disponible": True, "plan": "Free", "cuota": 100, "usadas": 37, "restantes": 63}
    cliente.get("/api/serpapi/cuenta")
    assert len(llamadas) == 1  # caché de 5 minutos

    aplicacion._cuenta.update(t=0.0, d=None)

    def falla(*a, **k):
        raise aplicacion.requests.ConnectionError("url con api_key=CLAVE-SECRETA-XYZ")

    monkeypatch.setattr(aplicacion.requests, "get", falla)
    texto = cliente.get("/api/serpapi/cuenta").get_data(as_text=True)
    assert "CLAVE-SECRETA-XYZ" not in texto and '"disponible":false' in texto.replace(" ", "")
    os.environ["SERPAPI_KEY"] = "clave-falsa"
    aplicacion._cuenta.update(t=0.0, d=None)


def test_exportar_consumo_csv(cliente):
    r = cliente.get("/api/consumo.csv")
    assert r.status_code == 200 and "text/csv" in r.content_type
    assert "Créditos usados" in r.get_data(as_text=True)


def test_la_pagina_carga_el_panel_y_sus_recursos(cliente):
    html = cliente.get("/").get_data(as_text=True)
    for recurso in ("analitica.css", "analitica.js", "echarts@5.5.1", "maplibre-gl@4.7.1"):
        assert recurso in html, recurso
    assert cliente.get("/static/analitica.js").status_code == 200
    assert cliente.get("/static/analitica.css").status_code == 200
    js = cliente.get("/static/analitica.js").get_data(as_text=True)
    assert "innerHTML" in js and "textContent" in js
    # las etiquetas de datos (ciudad, sector, nombre) nunca se insertan sin escapar en el DOM
    assert "esc(" in js and "window.Analitica" in js


# ------------------------------------------------------------------ vistas guardadas del panel

FILTROS_OK = {"preset": "3m", "desde": None, "hasta": None, "ciudad": ["Pereira"], "sector": [], "usuario": [],
              "prioridad": ["alta"], "oportunidad": [], "score": None,
              "ui": {"consumoModo": "mes", "heat": "tasa", "rend": "canal"}}


@pytest.fixture(scope="module")
def cliente_laura(cliente):
    import app as aplicacion
    r = cliente.post("/api/usuarios", headers=H, json={"usuario": "laura", "nombre": "Laura Gómez",
                                                        "password": "laura-clave-123", "rol": "usuario"})
    assert r.status_code in (201, 409)
    c = aplicacion.app.test_client()
    assert c.post("/login", data={"usuario": "laura", "password": "laura-clave-123"}).status_code == 302
    return c


def test_crear_listar_y_validar_vistas(cliente):
    r = cliente.post("/api/vistas", headers=H, json={"nombre": "  Pereira   alta  ", "filtros": FILTROS_OK})
    assert r.status_code == 201
    v = r.get_json()
    assert v["nombre"] == "Pereira alta" and v["propia"] and not v["compartida"] and v["filtros"]["ui"]["heat"] == "tasa"
    assert any(x["id"] == v["id"] for x in cliente.get("/api/vistas").get_json()["vistas"])
    # duplicado (sin distinguir mayúsculas), nombre vacío, filtros inválidos, CSRF
    assert cliente.post("/api/vistas", headers=H, json={"nombre": "PEREIRA ALTA", "filtros": FILTROS_OK}).status_code == 409
    assert cliente.post("/api/vistas", headers=H, json={"nombre": "  ", "filtros": FILTROS_OK}).status_code == 400
    assert cliente.post("/api/vistas", headers=H, json={"nombre": "x" * 61, "filtros": FILTROS_OK}).status_code == 400
    assert cliente.post("/api/vistas", json={"nombre": "Sin cabecera", "filtros": FILTROS_OK}).status_code == 403
    malos = [dict(FILTROS_OK, preset="hackeado"), dict(FILTROS_OK, desde="2026-13-45", preset="custom"),
             dict(FILTROS_OK, ciudad="no-es-lista"), dict(FILTROS_OK, ciudad=["a"] * 51),
             dict(FILTROS_OK, ciudad=[{"x": 1}]), dict(FILTROS_OK, score=[90, 10]), dict(FILTROS_OK, score=[0, 500]),
             dict(FILTROS_OK, score="alto"), "texto", None]
    for i, f in enumerate(malos):
        assert cliente.post("/api/vistas", headers=H, json={"nombre": f"mala {i}", "filtros": f}).status_code == 400, f


def test_los_filtros_se_normalizan_y_no_guardan_campos_extra(cliente):
    sucio = dict(FILTROS_OK, preset="6m", desde="2026-01-01", hasta="2026-02-01", extra="<script>x</script>",
                 ui={"consumoModo": "raro", "heat": "otro", "rend": 5, "malo": 1})
    v = cliente.post("/api/vistas", headers=H, json={"nombre": "Normalizada", "filtros": sucio}).get_json()
    f = v["filtros"]
    assert "extra" not in f and f["desde"] is None and f["hasta"] is None  # fechas solo en rango personalizado
    assert f["ui"] == {"consumoModo": "mes", "heat": "leads", "rend": "usuario"}
    custom = cliente.post("/api/vistas", headers=H, json={"nombre": "Personalizada", "filtros": dict(
        FILTROS_OK, preset="custom", desde="2026-01-01", hasta="2026-02-01", score=[60, 79])}).get_json()["filtros"]
    assert custom["desde"] == "2026-01-01" and custom["hasta"] == "2026-02-01" and custom["score"] == [60, 79]


def test_predeterminada_solo_una_por_usuario(cliente):
    a = cliente.post("/api/vistas", headers=H, json={"nombre": "Def A", "filtros": FILTROS_OK}).get_json()["id"]
    b = cliente.post("/api/vistas", headers=H, json={"nombre": "Def B", "filtros": FILTROS_OK}).get_json()["id"]
    assert cliente.patch(f"/api/vistas/{a}", headers=H, json={"predeterminada": True}).get_json()["predeterminada"] is True
    assert cliente.patch(f"/api/vistas/{b}", headers=H, json={"predeterminada": True}).get_json()["predeterminada"] is True
    estado = {v["id"]: v["predeterminada"] for v in cliente.get("/api/vistas").get_json()["vistas"]}
    assert estado[a] is False and estado[b] is True
    assert cliente.patch(f"/api/vistas/{b}", headers=H, json={}).status_code == 400
    assert cliente.patch(f"/api/vistas/{b}", json={"predeterminada": False}).status_code == 403  # CSRF


def test_compartir_privacidad_y_permisos(cliente, cliente_laura):
    privada = cliente.post("/api/vistas", headers=H, json={"nombre": "Solo admin", "filtros": FILTROS_OK}).get_json()["id"]
    comp = cliente.post("/api/vistas", headers=H, json={"nombre": "Para el equipo", "filtros": FILTROS_OK, "compartida": True}).get_json()["id"]
    vistas_laura = {v["nombre"]: v for v in cliente_laura.get("/api/vistas").get_json()["vistas"]}
    assert "Solo admin" not in vistas_laura                      # lo privado no se ve
    v = vistas_laura["Para el equipo"]
    assert v["propia"] is False and v["autor"] and v["predeterminada"] is False and v["puede_borrar"] is False
    # Laura no puede tocar la ajena: 404 si es privada (no revela que existe), 403 si es compartida
    assert cliente_laura.delete(f"/api/vistas/{privada}", headers=H).status_code == 404
    assert cliente_laura.patch(f"/api/vistas/{privada}", headers=H, json={"predeterminada": True}).status_code == 404
    assert cliente_laura.delete(f"/api/vistas/{comp}", headers=H).status_code == 403
    assert cliente_laura.patch(f"/api/vistas/{comp}", headers=H, json={"predeterminada": True}).status_code == 403
    # sus propias vistas: puede crear con el mismo nombre que otro usuario
    assert cliente_laura.post("/api/vistas", headers=H, json={"nombre": "Para el equipo", "filtros": FILTROS_OK}).status_code == 201
    # el admin sí puede eliminar una compartida de otro (moderación)
    mia = [v for v in cliente_laura.get("/api/vistas").get_json()["vistas"] if v["propia"]][0]
    assert cliente_laura.patch(f"/api/vistas/{mia['id']}", headers=H, json={"compartida": True}).get_json()["compartida"] is True
    assert cliente.delete(f"/api/vistas/{mia['id']}", headers=H).status_code == 200
    assert cliente.delete(f"/api/vistas/{mia['id']}", headers=H).status_code == 404
    assert cliente.delete(f"/api/vistas/{privada}", headers=H).status_code == 200


def test_limite_de_vistas_por_usuario(cliente_laura):
    import app as aplicacion
    creadas = 0
    for i in range(aplicacion.MAX_VISTAS_POR_USUARIO + 2):
        r = cliente_laura.post("/api/vistas", headers=H, json={"nombre": f"Lote {i}", "filtros": FILTROS_OK})
        creadas += r.status_code == 201
        if r.status_code == 400:
            assert "Máximo" in r.get_json()["error"]
            break
    assert 0 < creadas <= aplicacion.MAX_VISTAS_POR_USUARIO


def test_el_panel_conoce_al_usuario_para_las_vistas(cliente):
    d = cliente.get("/api/analitica/datos").get_json()
    assert d["yo"]["rol"] == "admin" and d["yo"]["id"]


# ------------------------------------------------------------------ correo, avisos de cuota y envío de propuestas

import socket  # noqa: E402

import alertas  # noqa: E402
import correo  # noqa: E402

_VARS_CORREO = ("RESEND_API_KEY", "SMTP_HOST", "SMTP_PUERTO", "SMTP_USUARIO", "SMTP_CLAVE", "SMTP_SEGURIDAD",
                "ALERTA_EMAIL_DESTINO", "ALERTA_UMBRALES", "EMAIL_REMITENTE", "EMAIL_RESPONDER_A", "APP_URL")


@pytest.fixture
def sin_correo(monkeypatch):
    for v in _VARS_CORREO:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(alertas, "_ultimo_fallo", {"t": 0.0})
    monkeypatch.setattr(alertas, "_ultima_prueba", {"t": 0.0})
    monkeypatch.setattr(alertas, "_real", {"t": 0.0, "d": None})
    _limpiar_avisos()
    return monkeypatch


def _limpiar_avisos():
    import db
    with db.engine.begin() as conn:
        conn.execute(db.alertas_enviadas.delete())


def _con_resend(mp, destino="duena@example.com"):
    mp.setenv("RESEND_API_KEY", "re_clave_de_prueba_123")
    mp.setenv("ALERTA_EMAIL_DESTINO", destino)


def _capturar(mp):
    enviados = []
    mp.setattr(correo, "enviar", lambda asunto, texto, html=None, destinos=None, reply_to=None:
               enviados.append({"asunto": asunto, "texto": texto, "html": html, "destinos": destinos, "reply_to": reply_to}))
    return enviados


def _sumar_consumo(n):
    import db
    from sqlalchemy import insert as _ins
    with db.engine.begin() as conn:
        conn.execute(_ins(db.consumo).values(fecha=db.ahora(), tipo="radar", creditos=n, ahorrados=0, ciudad="Test", sector="Test"))


def _cuota_para(mp, porcentaje_actual):
    """Fija una cuota tal que el consumo actual del mes represente ese porcentaje."""
    usados = alertas.situacion()["usados"]
    cuota = max(10, round(usados * 100 / porcentaje_actual)) if usados else 100
    mp.setenv("SERPAPI_CUOTA_MES", str(cuota))
    return cuota


# ---- correo
def test_correo_destinatarios_proveedor_y_mascara(sin_correo):
    mp = sin_correo
    assert correo.proveedor() is None and not correo.configurado()
    mp.setenv("ALERTA_EMAIL_DESTINO", "uno@example.com; malo, otro@example.org ,sin-arroba.com")
    assert correo.destinatarios() == ["uno@example.com", "otro@example.org"]
    mp.setenv("SMTP_HOST", "smtp.gmail.com")
    assert correo.proveedor() == "smtp" and correo.configurado()
    mp.setenv("RESEND_API_KEY", "re_x_123456")
    assert correo.proveedor() == "resend"          # la API tiene prioridad
    assert correo.enmascarar("jhony@gmail.com") == "j***@gmail.com"


def test_correo_limpia_credenciales_de_los_errores(sin_correo):
    sin_correo.setenv("SMTP_CLAVE", "abcd efgh ijkl mnop")
    sin_correo.setenv("RESEND_API_KEY", "re_SECRETA_987654")
    t = correo.limpiar("fallo con abcdefghijklmnop y abcd efgh ijkl mnop y re_SECRETA_987654")
    assert "abcd" not in t and "re_SECRETA" not in t and t.count("***") == 3


def test_correo_smtp_de_punta_a_punta(sin_correo):
    pytest.importorskip("aiosmtpd")
    from aiosmtpd.controller import Controller
    from email import message_from_bytes
    recibidos = []

    class Manejador:
        async def handle_DATA(self, server, session, envelope):
            recibidos.append((envelope.mail_from, envelope.rcpt_tos, message_from_bytes(envelope.content)))
            return "250 OK"

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    ctl = Controller(Manejador(), hostname="127.0.0.1", port=puerto)
    ctl.start()
    try:
        mp = sin_correo
        mp.setenv("SMTP_HOST", "127.0.0.1"); mp.setenv("SMTP_PUERTO", str(puerto)); mp.setenv("SMTP_SEGURIDAD", "ninguna")
        mp.setenv("EMAIL_REMITENTE", "Cazador Leads <avisos@example.com>")
        mp.setenv("ALERTA_EMAIL_DESTINO", "duena@example.com")
        correo.enviar("Aviso de prueba\r\nBcc: espia@example.com", "Hola\nmundo", "<p>Hola <b>mundo</b></p>", reply_to="respuestas@example.com")
    finally:
        ctl.stop()
    assert len(recibidos) == 1
    de, para, msg = recibidos[0]
    assert para == ["duena@example.com"] and msg["Reply-To"] == "respuestas@example.com"
    assert "Bcc" not in msg and "\n" not in msg["Subject"] and msg["Subject"].startswith("Aviso de prueba")  # sin inyección de cabeceras
    assert msg.is_multipart() and "Hola" in msg.get_payload(0).get_payload(decode=True).decode()


def test_correo_errores_claros_y_sin_secretos(sin_correo):
    mp = sin_correo
    with pytest.raises(correo.CorreoError, match="proveedor"):
        correo.enviar("a", "b", destinos=["x@example.com"])
    mp.setenv("RESEND_API_KEY", "re_x_123456")
    with pytest.raises(correo.CorreoError, match="destinatarios"):
        correo.enviar("a", "b")
    mp.delenv("RESEND_API_KEY"); mp.setenv("SMTP_HOST", "127.0.0.1"); mp.setenv("SMTP_PUERTO", "1"); mp.setenv("SMTP_SEGURIDAD", "ninguna")
    mp.setenv("SMTP_CLAVE", "clave-super-secreta")
    with pytest.raises(correo.CorreoError) as e:
        correo.enviar("a", "b", destinos=["x@example.com"])
    assert "clave-super-secreta" not in str(e.value)
    mp.delenv("SMTP_HOST"); mp.setenv("RESEND_API_KEY", "re_clave_123456")

    class R:
        status_code = 403
        def json(self): return {"message": "Domain not verified re_clave_123456"}

    mp.setattr(correo.requests, "post", lambda *a, **k: R())
    with pytest.raises(correo.CorreoError) as e2:
        correo.enviar("a", "b", destinos=["x@example.com"])
    assert "403" in str(e2.value) and "re_clave_123456" not in str(e2.value)


# ---- avisos de cuota
def test_aviso_no_hace_nada_si_el_correo_no_esta_configurado(sin_correo):
    enviados = _capturar(sin_correo)
    _cuota_para(sin_correo, 50); _sumar_consumo(1000)
    alertas.revisar()
    assert enviados == []


def test_aviso_al_80_por_ciento_una_sola_vez_al_mes(sin_correo):
    mp = sin_correo; _con_resend(mp); enviados = _capturar(mp)
    cuota = _cuota_para(mp, 50)
    alertas.revisar()
    assert enviados == []                                     # al 50% todavía no
    _sumar_consumo(int(cuota * 0.8) - alertas.situacion()["usados"] + 1)
    alertas.revisar(); alertas.revisar(); alertas.revisar()
    assert len(enviados) == 1                                 # una sola vez aunque se revise muchas
    e = enviados[0]
    assert "80%" in e["asunto"] or "8" in e["asunto"]
    assert str(cuota) in e["texto"] and "Proyección" in e["texto"] and "caché" in e["texto"] and e["destinos"] is None
    assert "<" not in e["texto"] and "re_clave" not in e["texto"] + (e["html"] or "")
    est = alertas.estado()
    assert est["configurado"] and est["destinos"] == ["d***@example.com"] and est["enviadas_mes"][0]["umbral"] == 80


def test_aviso_varios_umbrales_a_la_vez_envian_un_solo_correo(sin_correo):
    mp = sin_correo; _con_resend(mp); enviados = _capturar(mp)
    mp.setenv("ALERTA_UMBRALES", "50, 80 ,100,abc,500")
    assert alertas.umbrales() == [50, 80, 100]
    cuota = _cuota_para(mp, 30)
    _sumar_consumo(cuota - alertas.situacion()["usados"] + 5)   # salta de golpe por encima del 100%
    alertas.revisar(); alertas.revisar()
    assert len(enviados) == 1 and "agotaste" in enviados[0]["asunto"]
    assert len(alertas.estado()["enviadas_mes"]) == 3


def test_aviso_fallido_libera_la_marca_y_reintenta_despues(sin_correo):
    mp = sin_correo; _con_resend(mp)
    intentos = []

    def falla(*a, **k):
        intentos.append(1)
        raise correo.CorreoError("proveedor caído")

    mp.setattr(correo, "enviar", falla)
    cuota = _cuota_para(mp, 50)
    _sumar_consumo(int(cuota * 0.9) - alertas.situacion()["usados"])
    alertas.revisar()
    assert len(intentos) == 1 and alertas.estado()["enviadas_mes"] == []   # no quedó marcado como enviado
    alertas.revisar()
    assert len(intentos) == 1                                              # respeta el enfriamiento tras fallar
    mp.setattr(alertas, "_ultimo_fallo", {"t": 0.0})
    enviados = _capturar(mp)
    alertas.revisar()
    assert len(enviados) == 1 and len(alertas.estado()["enviadas_mes"]) == 1


def test_aviso_usa_el_consumo_real_de_la_cuenta_si_es_mayor(sin_correo):
    import db
    with db.engine.begin() as conn:
        conn.execute(db.consumo.delete())                    # parte de cero: la app no ha registrado nada
    mp = sin_correo; _con_resend(mp); enviados = _capturar(mp)
    mp.setenv("SERPAPI_CUOTA_MES", "100000")                 # la app, por sí sola, estaría lejísimos del umbral
    alertas.recordar_cuenta({"disponible": True, "usadas": 85, "cuota": 100, "restantes": 15, "plan": "Free"})
    alertas.revisar()
    assert len(enviados) == 1 and "85" in enviados[0]["asunto"] and "100" in enviados[0]["asunto"]


def test_registrar_consumo_dispara_el_aviso(sin_correo):
    import db
    mp = sin_correo; _con_resend(mp); enviados = _capturar(mp)
    cuota = _cuota_para(mp, 50)
    db.registrar_consumo("radar", int(cuota * 0.85) - alertas.situacion()["usados"] + 1, 0, None, "Cali", "abogados")
    assert len(enviados) == 1


def test_enlace_al_panel_solo_si_hay_url(sin_correo):
    s = alertas.situacion()
    assert "Panel:" not in alertas.construir_mensaje(80, s)[1]
    sin_correo.setenv("APP_URL", "https://mi-app.onrender.com/")
    assert "Panel: https://mi-app.onrender.com/#analitica" in alertas.construir_mensaje(80, s)[1]


def test_correo_de_prueba_solo_admin_y_con_limite(sin_correo, cliente, cliente_laura):
    mp = sin_correo
    assert cliente.post("/api/alertas/prueba", headers=H).status_code == 502          # sin configurar
    _con_resend(mp); enviados = _capturar(mp)
    assert cliente_laura.post("/api/alertas/prueba", headers=H).status_code == 403    # no es admin
    assert cliente.post("/api/alertas/prueba").status_code == 403                     # CSRF
    r = cliente.post("/api/alertas/prueba", headers=H)
    assert r.status_code == 200 and r.get_json()["destinos"] == ["d***@example.com"]
    assert enviados[0]["asunto"].startswith("[PRUEBA]")
    assert cliente.post("/api/alertas/prueba", headers=H).status_code == 429          # una prueba cada 30 s
    est = cliente.get("/api/alertas/estado").get_json()
    assert est["configurado"] and est["puede_enviar"] and "d***@example.com" in est["destinos"] and "duena" not in str(est)


# ---- envío de propuestas a leads
def _crear_lead(email="cliente@negocio.co", estado="nuevo", nombre="Negocio Propuesta"):
    import db
    from sqlalchemy import insert as _ins
    clave = f"test-envio-{nombre}-{email}-{estado}"
    with db.engine.begin() as conn:
        return conn.execute(_ins(db.leads).values(clave=clave, nombre=nombre, email=email, ciudad="Cali", nicho="abogados", pais="Colombia",
                                                    estado=estado, creado_en=db.ahora(), actualizado_en=db.ahora(), score=70, prioridad="alta")).inserted_primary_key[0]


BODY_OK = {"asunto": "Idea para tu web", "cuerpo": "Hola, vi que tu negocio no tiene web propia y quería proponerte una idea concreta.",
           "confirmar": True, "plantilla": "sin_web:email:a"}


def test_enviar_propuesta_al_lead_con_todas_las_salvaguardas(sin_correo, cliente):
    import app as aplicacion
    import db
    from sqlalchemy import select as _sel
    mp = sin_correo; enviados = _capturar(mp)
    mp.setenv("REMITENTE_NOMBRE", "Jhony"); mp.setenv("AGENCIA_NOMBRE", "Mi Agencia"); mp.setenv("EMAIL_RESPONDER_A", "ventas@miagencia.co")
    lid = _crear_lead()
    url = f"/api/leads/{lid}/enviar-email"
    assert cliente.post(url, json=BODY_OK).status_code == 403                                            # CSRF
    assert cliente.post(url, headers=H, json=BODY_OK).status_code == 400                                 # correo sin configurar
    mp.setenv("RESEND_API_KEY", "re_clave_de_prueba_123")
    assert cliente.post(url, headers=H, json=dict(BODY_OK, confirmar=False)).status_code == 400          # sin confirmación explícita
    assert cliente.post(url, headers=H, json=dict(BODY_OK, asunto="  ")).status_code == 400
    assert cliente.post(url, headers=H, json=dict(BODY_OK, cuerpo="corto")).status_code == 400
    r = cliente.post(url, headers=H, json=dict(BODY_OK, cuerpo=BODY_OK["cuerpo"] + " Soy [TU NOMBRE] de [TU AGENCIA]."))
    assert r.status_code == 400 and "REMITENTE_NOMBRE" in r.get_json()["error"]                          # no sale con placeholders
    assert enviados == []
    ok = cliente.post(url, headers=H, json=BODY_OK)
    assert ok.status_code == 200
    out = ok.get_json()
    assert out["estado"] == "contactado" and out["canal_contacto"] == "email" and out["proximo_seguimiento"]
    assert out["envios_restantes_hoy"] >= 0 and any(h["canal"] == "email" for h in out["historial"])
    e = enviados[0]
    assert e["destinos"] == ["cliente@negocio.co"] and e["reply_to"] == "ventas@miagencia.co"             # solo al email del lead
    assert "Mi Agencia" in e["texto"] and "responde «no»" in e["texto"] and BODY_OK["cuerpo"] in e["texto"]  # firma y baja
    with db.engine.connect() as conn:
        fila = conn.execute(_sel(db.envios).where(db.envios.c.lead_id == lid)).mappings().one()
    assert fila["estado"] == "enviado" and fila["destino"] == "cliente@negocio.co" and fila["usuario_id"]
    assert cliente.post(url, headers=H, json=BODY_OK).status_code == 409                                 # no repetir en 24 h


def test_no_envia_a_leads_sin_email_cerrados_o_descartados(sin_correo, cliente):
    mp = sin_correo; enviados = _capturar(mp); mp.setenv("RESEND_API_KEY", "re_clave_de_prueba_123")
    sin_email = _crear_lead(email="", nombre="Sin Email")
    descartado = _crear_lead(estado="descartado", nombre="Descartado")
    cerrado = _crear_lead(estado="cerrado", nombre="Cerrado")
    malo = _crear_lead(email="no-es-un-email", nombre="Email Malo")
    for lid in (sin_email, descartado, cerrado, malo):
        assert cliente.post(f"/api/leads/{lid}/enviar-email", headers=H, json=BODY_OK).status_code == 400
    assert cliente.post("/api/leads/999999/enviar-email", headers=H, json=BODY_OK).status_code == 404
    assert enviados == []


def test_limite_diario_de_envios(sin_correo, cliente):
    import app as aplicacion
    mp = sin_correo; enviados = _capturar(mp); mp.setenv("RESEND_API_KEY", "re_clave_de_prueba_123")
    mp.setattr(aplicacion, "ENVIO_MAX_DIA", aplicacion._enviados_hoy() + 1)
    a, b = _crear_lead(nombre="Lead Limite A", email="a@limite.co"), _crear_lead(nombre="Lead Limite B", email="b@limite.co")
    assert cliente.post(f"/api/leads/{a}/enviar-email", headers=H, json=BODY_OK).status_code == 200
    r = cliente.post(f"/api/leads/{b}/enviar-email", headers=H, json=BODY_OK)
    assert r.status_code == 429 and "Límite diario" in r.get_json()["error"]
    assert len(enviados) == 1


def test_error_del_proveedor_se_registra_y_no_marca_contacto(sin_correo, cliente):
    import db
    from sqlalchemy import select as _sel
    mp = sin_correo; mp.setenv("RESEND_API_KEY", "re_clave_de_prueba_123")

    def falla(*a, **k):
        raise correo.CorreoError("Resend rechazó el envío (403): dominio no verificado")

    mp.setattr(correo, "enviar", falla)
    lid = _crear_lead(nombre="Lead Falla", email="falla@negocio.co")
    r = cliente.post(f"/api/leads/{lid}/enviar-email", headers=H, json=BODY_OK)
    assert r.status_code == 502 and "dominio no verificado" in r.get_json()["error"]
    assert cliente.get(f"/api/leads/{lid}").get_json()["estado"] == "nuevo"           # no cuenta como contactado
    with db.engine.connect() as conn:
        fila = conn.execute(_sel(db.envios).where(db.envios.c.lead_id == lid)).mappings().one()
    assert fila["estado"] == "error" and "403" in fila["error"]
    mp.setattr(correo, "enviar", lambda *a, **k: None)
    assert cliente.post(f"/api/leads/{lid}/enviar-email", headers=H, json=BODY_OK).status_code == 200   # un error no bloquea el reintento
