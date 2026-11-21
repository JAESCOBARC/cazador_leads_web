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
