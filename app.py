#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cazador Leads Web — API Flask
Expone la funcionalidad de búsqueda como servicio web
"""

import os
import csv
import io
import json
import re
import secrets
import time

import requests
from datetime import date, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from pathlib import Path
from sqlalchemy import select, insert, update, func, and_, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

import db
import escaner
import mensajes
import radar
import redes
from cazador_leads import CazadorLeads

app = Flask(__name__, template_folder='templates', static_folder='static')
# Sin CORS: la interfaz se sirve desde este mismo origen.

app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=bool(os.environ.get('RENDER')),
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)

BASE_DIR = Path(__file__).parent

db.init_db()

# ---------------------------------------------------------------- Autenticación

_intentos = {}  # ip -> (fallos, primer_fallo_ts)
MAX_FALLOS, VENTANA = 5, 600


def usuario_actual():
    uid = session.get('uid')
    if not uid:
        return None
    with db.engine.connect() as conn:
        row = conn.execute(select(db.usuarios).where(
            db.usuarios.c.id == uid, db.usuarios.c.activo.is_(True))).mappings().first()
    return dict(row) if row else None


@app.before_request
def exigir_login():
    if request.endpoint in ('login', 'static') or request.endpoint is None:
        return None
    user = usuario_actual()
    if user is None:
        session.clear()
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Sesión no iniciada'}), 401
        return redirect(url_for('login'))
    request.user = user
    # Anti-CSRF: las peticiones que modifican datos deben llevar una cabecera propia
    # (un sitio externo no puede enviarla sin permiso CORS, y aquí no hay CORS).
    if (request.method in ('POST', 'PATCH', 'PUT', 'DELETE') and request.path.startswith('/api/')
            and request.headers.get('X-Requested-With') != 'fetch'):
        return jsonify({'error': 'Petición no permitida'}), 403
    return None


def solo_admin(fn):
    @wraps(fn)
    def inner(*a, **kw):
        if request.user['rol'] != 'admin':
            return jsonify({'error': 'Solo administradores'}), 403
        return fn(*a, **kw)
    return inner


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        ip = request.remote_addr or '?'
        fallos, desde = _intentos.get(ip, (0, time.time()))
        if time.time() - desde > VENTANA:
            fallos, desde = 0, time.time()
        if fallos >= MAX_FALLOS:
            error = 'Demasiados intentos. Espera unos minutos.'
        else:
            nombre = (request.form.get('usuario') or '').strip().lower()
            with db.engine.connect() as conn:
                row = conn.execute(select(db.usuarios).where(
                    db.usuarios.c.usuario == nombre, db.usuarios.c.activo.is_(True))).mappings().first()
            if row and check_password_hash(row['password_hash'], request.form.get('password') or ''):
                _intentos.pop(ip, None)
                session.clear()
                session['uid'] = row['id']
                session.permanent = True
                return redirect(url_for('index'))
            _intentos[ip] = (fallos + 1, desde)
            error = 'Usuario o contraseña incorrectos'
    return render_template('login.html', error=error)


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
def index():
    """Sirve la página principal"""
    return render_template('index.html')


@app.route('/api/yo')
def yo():
    u = request.user
    return jsonify({'id': u['id'], 'usuario': u['usuario'], 'nombre': u['nombre'], 'rol': u['rol']})


@app.route('/api/sectores')
def sectores():
    return jsonify({'sectores': escaner.SECTORES, 'coberturas': {
        k: {'puntos': p, 'paginas': g, 'creditos_por_sector': p * g} for k, (p, g) in radar.COBERTURAS.items()}})


@app.route('/api/geocodificar')
def geocodificar():
    """Resuelve ciudad+país a coordenadas (para mover el mapa). Usa la misma caché que el radar."""
    ciudad = (request.args.get('ciudad') or '').strip()
    pais = (request.args.get('pais') or '').strip()
    if not ciudad or not pais:
        return jsonify({'error': 'Ciudad y país son requeridos'}), 400
    try:
        geo = CazadorLeads().geocodificar(ciudad, pais)
    except Exception as e:  # noqa: BLE001
        return jsonify({'error': f'No se pudo ubicar: {e}'}), 502
    if not geo:
        return jsonify({'error': 'Ubicación no encontrada'}), 404
    return jsonify({'lat': geo['lat'], 'lon': geo['lon'], 'nombre': geo['display_name']})


@app.route('/api/radar', methods=['POST'])
def lanzar_radar():
    """Lanza una exploración en segundo plano y devuelve el id para consultar el progreso."""
    d = request.get_json(silent=True) or {}
    ciudad = (d.get('ciudad') or '').strip()
    pais = (d.get('pais') or '').strip()
    sectores_ = [str(x).strip() for x in (d.get('sectores') or []) if str(x).strip()]
    sectores_ = list(dict.fromkeys(sectores_))[:radar.MAX_SECTORES]
    cobertura = d.get('cobertura') if d.get('cobertura') in radar.COBERTURAS else 'normal'
    if not ciudad or not pais or not sectores_:
        return jsonify({'error': 'Ciudad, país y al menos un sector son requeridos'}), 400
    job_id = radar.iniciar(ciudad, pais, sectores_, cobertura, bool(d.get('analizar_webs', True)),
                           request.user['id'])
    return jsonify({'job_id': job_id, 'creditos_estimados': radar.creditos_estimados(len(sectores_), cobertura)}), 202


@app.route('/api/radar/<job_id>')
def estado_radar(job_id):
    job = radar.estado(job_id)
    if not job or job['user_id'] != request.user['id'] or job.get('tipo') == 'redes':
        return jsonify({'error': 'Exploración no encontrada'}), 404
    out = {'estado': job['estado'], 'etapa': job['etapa'], 'progreso': job['progreso'], 'error': job['error']}
    if job['estado'] == 'listo':
        res = dict(job['resultado'])
        ids = res.pop('lead_ids')
        if ids:
            with db.engine.connect() as conn:
                nombres = _nombres_usuarios(conn)
                rows = conn.execute(select(db.leads).where(db.leads.c.id.in_(ids))).mappings().all()
            por_id = {r['id']: _lead_dict(r, nombres) for r in rows}
            res['leads'] = sorted((por_id[i] for i in ids if i in por_id), key=lambda l: -(l['score'] or 0))
        else:
            res['leads'] = []
        out['resultado'] = res
    return jsonify(out)


# ---------------------------------------------------------------- Leads

def _iso(dt):
    return dt.isoformat() if dt else None


def _lead_dict(r, nombres):
    return {
        'id': r['id'], 'nombre': r['nombre'], 'telefono': r['telefono'] or '', 'email': r['email'] or '',
        'whatsapp': r['whatsapp'] or '', 'redes_sociales': r['redes_sociales'] or '',
        'direccion': r['direccion'] or '', 'nicho': r['nicho'] or '', 'ciudad': r['ciudad'] or '',
        'pais': r['pais'] or '', 'canal_recomendado': r['canal_recomendado'],
        'asunto': r['asunto'] or '', 'cuerpo': r['cuerpo'] or '', 'estado': r['estado'],
        'canal_contacto': r['canal_contacto'], 'asignado_a': r['asignado_a'],
        'asignado_nombre': nombres.get(r['asignado_a']), 'contactado_en': _iso(r['contactado_en']),
        'proximo_seguimiento': _iso(r['proximo_seguimiento']), 'notas': r['notas'] or '',
        'creado_en': _iso(r['creado_en']),
        'rating': r['rating'], 'resenas': r['resenas'], 'tipo': r['tipo'] or '', 'lat': r['lat'], 'lon': r['lon'],
        'web_url': r['web_url'] or '', 'tiene_web': r['tiene_web'], 'maps_url': r['maps_url'] or '',
        'score': r['score'] or 0, 'prioridad': r['prioridad'], 'ticket': r['ticket'],
        'competidores': r['competidores'], 'plantilla': r['plantilla'],
        'oportunidades': _json(r['oportunidades'], []), 'diagnostico': _json(r['diagnostico'], {}),
        'escaneado_en': _iso(r['escaneado_en']),
    }


def _json(v, defecto):
    try:
        return json.loads(v) if v else defecto
    except ValueError:
        return defecto


def _nombres_usuarios(conn):
    return {u.id: u.nombre for u in conn.execute(select(db.usuarios.c.id, db.usuarios.c.nombre))}


@app.route('/api/leads')
def listar_leads():
    L = db.leads
    cond = []
    estado = request.args.get('estado')
    if estado in db.ESTADOS:
        cond.append(L.c.estado == estado)
    asignado = request.args.get('asignado')
    if asignado == 'ninguno':
        cond.append(L.c.asignado_a.is_(None))
    elif asignado and asignado.isdigit():
        cond.append(L.c.asignado_a == int(asignado))
    if request.args.get('seguimiento') == 'pendiente':
        cond.append(and_(L.c.proximo_seguimiento.isnot(None), L.c.proximo_seguimiento <= date.today(),
                         L.c.estado.in_(['contactado', 'respondio'])))
    prioridad = request.args.get('prioridad')
    if prioridad in db.PRIORIDADES:
        cond.append(L.c.prioridad == prioridad)
    opp = request.args.get('oportunidad')
    if opp in escaner.OPORTUNIDADES:
        cond.append(L.c.oportunidades.like('%"tipo": "' + opp + '"%'))
    q = (request.args.get('q') or '').strip().lower()
    if q:
        like = f'%{q}%'
        cond.append(or_(func.lower(L.c.nombre).like(like), func.lower(L.c.telefono).like(like),
                        func.lower(L.c.nicho).like(like), func.lower(L.c.ciudad).like(like)))
    with db.engine.connect() as conn:
        nombres = _nombres_usuarios(conn)
        rows = conn.execute(select(L).where(*cond).order_by(func.coalesce(L.c.score, 0).desc(), L.c.creado_en.desc(), L.c.id.desc())
                            .limit(500)).mappings().all()
    return jsonify({'leads': [_lead_dict(r, nombres) for r in rows]})


@app.route('/api/leads/<int:lead_id>', methods=['GET'])
def detalle_lead(lead_id):
    with db.engine.connect() as conn:
        nombres = _nombres_usuarios(conn)
        r = conn.execute(select(db.leads).where(db.leads.c.id == lead_id)).mappings().first()
        if not r:
            return jsonify({'error': 'Lead no encontrado'}), 404
        hist = conn.execute(select(db.contactos).where(db.contactos.c.lead_id == lead_id)
                            .order_by(db.contactos.c.fecha.desc(), db.contactos.c.id.desc())).mappings().all()
    d = _lead_dict(r, nombres)
    d['historial'] = [{'estado': h['estado'], 'canal': h['canal'], 'nota': h['nota'] or '',
                       'usuario': nombres.get(h['usuario_id'], '—'), 'fecha': _iso(h['fecha'])} for h in hist]
    return jsonify(d)


@app.route('/api/leads/<int:lead_id>', methods=['PATCH'])
def actualizar_lead(lead_id):
    """Cambia estado / asignación / seguimiento / notas y registra el contacto.
    Al pasar de 'nuevo' a cualquier otro estado, el lead queda asignado a un usuario
    (el indicado en `asignado_a` o, si no se indica, el usuario que lo marca)."""
    data = request.get_json(silent=True) or {}
    L = db.leads
    with db.engine.begin() as conn:
        lead = conn.execute(select(L).where(L.c.id == lead_id)).mappings().first()
        if not lead:
            return jsonify({'error': 'Lead no encontrado'}), 404

        cambios = {}
        estado = data.get('estado', lead['estado'])
        if estado not in db.ESTADOS:
            return jsonify({'error': 'Estado no válido'}), 400

        canal = data.get('canal_contacto', lead['canal_contacto'])
        if canal not in (None, '') and canal not in db.CANALES:
            return jsonify({'error': 'Canal no válido'}), 400

        asignado = lead['asignado_a']
        if 'asignado_a' in data:
            asignado = data['asignado_a']
            if asignado in ('', None):
                asignado = None
            else:
                try:
                    asignado = int(asignado)
                except (TypeError, ValueError):
                    return jsonify({'error': 'Usuario asignado no válido'}), 400
                ok = conn.execute(select(db.usuarios.c.id).where(
                    db.usuarios.c.id == asignado, db.usuarios.c.activo.is_(True))).first()
                if not ok:
                    return jsonify({'error': 'El usuario asignado no existe o está inactivo'}), 400
        if estado != 'nuevo' and asignado is None:
            asignado = request.user['id']

        if 'proximo_seguimiento' in data:
            v = data['proximo_seguimiento']
            try:
                cambios['proximo_seguimiento'] = date.fromisoformat(v) if v else None
            except (TypeError, ValueError):
                return jsonify({'error': 'Fecha de seguimiento no válida'}), 400
        if 'notas' in data:
            cambios['notas'] = (data['notas'] or '')[:5000]

        cambio_estado = estado != lead['estado']
        if (cambio_estado and estado == 'contactado' and 'proximo_seguimiento' not in data
                and not lead['proximo_seguimiento']):
            cambios['proximo_seguimiento'] = date.today() + timedelta(days=mensajes.PASOS_DIAS[0])
        cambios.update(estado=estado, asignado_a=asignado, canal_contacto=canal or None,
                       actualizado_en=db.ahora())
        if cambio_estado and estado != 'nuevo' and not lead['contactado_en']:
            cambios['contactado_en'] = db.ahora()

        conn.execute(update(L).where(L.c.id == lead_id).values(**cambios))
        if cambio_estado:
            conn.execute(insert(db.contactos).values(
                lead_id=lead_id, usuario_id=request.user['id'], estado=estado, canal=canal or None,
                nota=(data.get('nota') or '')[:2000], fecha=db.ahora(),
                plantilla=(data.get('plantilla') or '')[:60] or None))
    return detalle_lead(lead_id)


@app.route('/api/leads/<int:lead_id>/mensaje')
def mensaje_lead(lead_id):
    """Mensaje para el ángulo/canal/paso pedidos (por defecto: principal, canal real y paso según
    los contactos ya registrados)."""
    with db.engine.connect() as conn:
        r = conn.execute(select(db.leads).where(db.leads.c.id == lead_id)).mappings().first()
        if not r:
            return jsonify({'error': 'Lead no encontrado'}), 404
        enviados = conn.execute(select(func.count()).select_from(db.contactos).where(
            db.contactos.c.lead_id == lead_id, db.contactos.c.estado == 'contactado')).scalar()
    paso = request.args.get('paso')
    paso = int(paso) if paso and paso.isdigit() else min(enviados, 2)
    lead = radar.lead_desde_fila(r)
    m = mensajes.construir(lead, angulo=request.args.get('angulo'), canal=request.args.get('canal'),
                           paso=min(paso, 2), variante=request.args.get('variante'))
    m['toques'] = enviados
    return jsonify(m)


@app.route('/api/leads/<int:lead_id>/toque', methods=['POST'])
def registrar_toque(lead_id):
    """Registra un nuevo contacto (mensaje inicial o seguimiento) y agenda el siguiente
    según la secuencia: día +3 tras el primero, +4 tras el seguimiento, luego nada."""
    d = request.get_json(silent=True) or {}
    canal = d.get('canal')
    if canal not in db.CANALES:
        return jsonify({'error': 'Canal no válido'}), 400
    L = db.leads
    with db.engine.begin() as conn:
        lead = conn.execute(select(L).where(L.c.id == lead_id)).mappings().first()
        if not lead:
            return jsonify({'error': 'Lead no encontrado'}), 404
        if lead['estado'] in ('cerrado', 'descartado'):
            return jsonify({'error': 'Este lead ya está cerrado o descartado'}), 400
        previos = conn.execute(select(func.count()).select_from(db.contactos).where(
            db.contactos.c.lead_id == lead_id, db.contactos.c.estado == 'contactado')).scalar()
        estado = lead['estado'] if lead['estado'] != 'nuevo' else 'contactado'
        dias = mensajes.PASOS_DIAS.get(previos)
        cambios = dict(estado=estado, canal_contacto=canal, actualizado_en=db.ahora(),
                       asignado_a=lead['asignado_a'] or request.user['id'],
                       proximo_seguimiento=date.today() + timedelta(days=dias) if dias else None)
        if not lead['contactado_en']:
            cambios['contactado_en'] = db.ahora()
        conn.execute(update(L).where(L.c.id == lead_id).values(**cambios))
        conn.execute(insert(db.contactos).values(
            lead_id=lead_id, usuario_id=request.user['id'], estado='contactado',
            canal=canal, nota=(d.get('nota') or '')[:2000], fecha=db.ahora(),
            plantilla=(d.get('plantilla') or '')[:60] or None))
    return detalle_lead(lead_id)


@app.route('/api/leads/<int:lead_id>/redes', methods=['POST'])
def buscar_redes(lead_id):
    """Busca el Instagram/Facebook del negocio en Google (1 crédito de SerpAPI, con caché) y guarda
    lo que el propio negocio publicó en su bio: perfil, email, WhatsApp, teléfono."""
    L = db.leads
    with db.engine.connect() as conn:
        r = conn.execute(select(L).where(L.c.id == lead_id)).mappings().first()
    if not r:
        return jsonify({'error': 'Lead no encontrado'}), 404
    try:
        res = redes.buscar_perfiles(r['nombre'], r['ciudad'] or '', cache=radar.CacheDB())
    except redes.RedesError as e:
        return jsonify({'error': str(e)}), 502

    db.registrar_consumo('redes', res['creditos'], 0 if res['creditos'] else 1, request.user['id'],
                         r['ciudad'], r['nicho'], lead_id, 'manual')
    radar.aplicar_redes(lead_id, res)
    out = detalle_lead(lead_id).get_json()
    out['redes_resultado'] = res
    return jsonify(out)


@app.route('/api/redes/lote/candidatos')
def candidatos_lote():
    prioridad = request.args.get('prioridad')
    return jsonify({'candidatos': radar.contar_candidatos_redes(prioridad), 'max_creditos': radar.LOTE_MAX_CREDITOS})


@app.route('/api/redes/lote', methods=['POST'])
def lanzar_lote_redes():
    """Busca redes de varios leads (nuevos, sin email), de mayor a menor puntuación, hasta un tope de
    créditos de SerpAPI fijado por quien lanza el lote. Sin IA: solo consultas a Google."""
    d = request.get_json(silent=True) or {}
    prioridad = d.get('prioridad') if d.get('prioridad') in db.PRIORIDADES else None
    try:
        tope = int(d.get('max_creditos'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Indica un tope de créditos (número entero)'}), 400
    if tope < 1:
        return jsonify({'error': 'El tope debe ser al menos 1 crédito'}), 400
    key = os.environ.get('SERPAPI_KEY', '')
    if not key or key == 'tu_api_key_aqui':
        return jsonify({'error': 'SERPAPI_KEY no configurada en .env'}), 400
    previo = radar.en_curso_lote(request.user['id'])
    if previo:
        return jsonify({'job_id': previo['id'], 'ya_en_curso': True}), 200
    n = radar.contar_candidatos_redes(prioridad)
    if not n:
        return jsonify({'error': 'No hay leads nuevos sin email pendientes de buscar con ese filtro'}), 400
    job_id = radar.iniciar_lote_redes(request.user['id'], prioridad, tope)
    return jsonify({'job_id': job_id, 'candidatos': n, 'max_creditos': min(tope, radar.LOTE_MAX_CREDITOS)}), 202


@app.route('/api/redes/lote/<job_id>')
def estado_lote_redes(job_id):
    job = radar.estado(job_id)
    if not job or job['user_id'] != request.user['id'] or job.get('tipo') != 'redes':
        return jsonify({'error': 'Búsqueda no encontrada'}), 404
    return jsonify({'estado': job['estado'], 'etapa': job['etapa'], 'progreso': job['progreso'],
                    'error': job['error'], 'resultado': job['resultado']})


@app.route('/api/leads.csv')
def exportar_csv():
    with db.engine.connect() as conn:
        nombres = _nombres_usuarios(conn)
        rows = conn.execute(select(db.leads).order_by(db.leads.c.id)).mappings().all()

    def seguro(v):  # evita inyección de fórmulas al abrir en Excel
        v = '' if v is None else str(v)
        return "'" + v if v[:1] in ('=', '+', '-', '@', '\t', '\r') else v

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Nombre', 'Teléfono', 'Email', 'Dirección', 'Nicho', 'Ciudad', 'País', 'Estado',
                'Canal contacto', 'Asignado a', 'Contactado', 'Próximo seguimiento', 'Notas',
                'Prioridad', 'Score', 'Oportunidades', 'Web', 'Rating', 'Reseñas'])
    for r in rows:
        w.writerow([seguro(x) for x in (
            r['nombre'], r['telefono'], r['email'], r['direccion'], r['nicho'], r['ciudad'], r['pais'],
            r['estado'], r['canal_contacto'], nombres.get(r['asignado_a'], ''),
            _iso(r['contactado_en']), _iso(r['proximo_seguimiento']), r['notas'], r['prioridad'], r['score'],
            ', '.join(o['titulo'] for o in _json(r['oportunidades'], [])), r['web_url'], r['rating'],
            r['resenas'])])
    return Response('﻿' + buf.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=leads.csv'})


# ---------------------------------------------------------------- Analítica

def por_oportunidad(rows):
    """Qué tipo de oportunidad convierte mejor (un lead cuenta en cada oportunidad que tiene)."""
    g = {}
    for r in rows:
        for o in _json(r['oportunidades'], []):
            d = g.setdefault(o['tipo'], {'nombre': o['titulo'], 'total': 0, 'contactados': 0,
                                         'respondieron': 0, 'cerrados': 0})
            d['total'] += 1
            d['contactados'] += r['estado'] != 'nuevo'
            d['respondieron'] += r['estado'] in ('respondio', 'reunion', 'cerrado')
            d['cerrados'] += r['estado'] == 'cerrado'
    out = sorted(g.values(), key=lambda d: -d['total'])
    for d in out:
        d['tasa_respuesta'] = round(100 * d['respondieron'] / d['contactados'], 1) if d['contactados'] else 0.0
    return out


@app.route('/api/analitica')
def analitica():
    with db.engine.connect() as conn:
        nombres = _nombres_usuarios(conn)
        rows = conn.execute(select(db.leads)).mappings().all()
        ev = conn.execute(select(db.contactos.c.estado, db.contactos.c.fecha)).all()

    contactados = [r for r in rows if r['estado'] != 'nuevo']
    respondieron = [r for r in rows if r['estado'] in ('respondio', 'reunion', 'cerrado')]
    cerrados = [r for r in rows if r['estado'] == 'cerrado']

    def pct(a, b):
        return round(100 * a / b, 1) if b else 0.0

    def agrupar(clave):
        g = {}
        for r in rows:
            k = clave(r) or '—'
            d = g.setdefault(k, {'nombre': k, 'total': 0, 'contactados': 0, 'respondieron': 0, 'cerrados': 0})
            d['total'] += 1
            d['contactados'] += r['estado'] != 'nuevo'
            d['respondieron'] += r['estado'] in ('respondio', 'reunion', 'cerrado')
            d['cerrados'] += r['estado'] == 'cerrado'
        out = list(g.values())
        for d in out:
            d['tasa_respuesta'] = pct(d['respondieron'], d['contactados'])
        return sorted(out, key=lambda d: (-d['total'], d['nombre']))

    # Contactos por semana (últimas 8, lunes como inicio)
    hoy = date.today()
    lunes = hoy - timedelta(days=hoy.weekday())
    semanas = [lunes - timedelta(weeks=i) for i in range(7, -1, -1)]
    conteo = {s: 0 for s in semanas}
    for estado, fecha in ev:
        if estado == 'contactado' and fecha:
            s = fecha.date() - timedelta(days=fecha.date().weekday())
            if s in conteo:
                conteo[s] += 1

    pendientes = sum(1 for r in rows if r['proximo_seguimiento'] and r['proximo_seguimiento'] <= hoy
                     and r['estado'] in ('contactado', 'respondio'))

    por_usuario = agrupar(lambda r: nombres.get(r['asignado_a']) if r['asignado_a'] else None)
    for d in por_usuario:
        if d['nombre'] == '—':
            d['nombre'] = 'Sin asignar'

    return jsonify({
        'totales': {
            'leads': len(rows), 'contactados': len(contactados), 'respondieron': len(respondieron),
            'cerrados': len(cerrados), 'tasa_contacto': pct(len(contactados), len(rows)),
            'tasa_respuesta': pct(len(respondieron), len(contactados)),
            'tasa_cierre': pct(len(cerrados), len(contactados)), 'seguimientos_pendientes': pendientes,
        },
        'embudo': [{'estado': e, 'total': sum(1 for r in rows if r['estado'] == e)} for e in db.ESTADOS],
        'por_canal': [d for d in agrupar(lambda r: r['canal_contacto']) if d['nombre'] != '—'],
        'por_nicho': agrupar(lambda r: r['nicho'])[:10],
        'por_ciudad': agrupar(lambda r: r['ciudad'])[:10],
        'por_prioridad': agrupar(lambda r: (r['prioridad'] or '').capitalize()),
        'por_plantilla': agrupar(lambda r: r['plantilla'])[:12],
        'por_oportunidad': por_oportunidad(rows),
        'por_usuario': por_usuario,
        'por_semana': [{'semana': s.isoformat(), 'total': conteo[s]} for s in semanas],
    })


# ---------------------------------------------------------------- Panel analítico

CUOTA_MES = max(1, int(os.environ.get('SERPAPI_CUOTA_MES', '100') or 100))
_cuenta = {'t': 0.0, 'd': None}


def _dt(v):
    return v.isoformat() if v else None


@app.route('/api/analitica/datos')
def analitica_datos():
    """Registros compactos para que el panel filtre y recalcule en el navegador (filtros cruzados)."""
    L = db.leads
    with db.engine.connect() as conn:
        nombres = _nombres_usuarios(conn)
        leads_ = conn.execute(select(
            L.c.id, L.c.nombre, L.c.creado_en, L.c.estado, L.c.contactado_en, L.c.canal_contacto, L.c.asignado_a,
            L.c.nicho, L.c.ciudad, L.c.prioridad, L.c.score, L.c.ticket, L.c.oportunidades, L.c.plantilla, L.c.email,
            L.c.rating, L.c.resenas, L.c.proximo_seguimiento
        ).order_by(L.c.id.desc()).limit(5000)).mappings().all()
        eventos = conn.execute(select(db.contactos.c.lead_id, db.contactos.c.estado, db.contactos.c.fecha,
                                      db.contactos.c.usuario_id, db.contactos.c.canal)
                               .order_by(db.contactos.c.id.desc()).limit(30000)).all()
        consumo_ = conn.execute(select(db.consumo).order_by(db.consumo.c.id.desc()).limit(30000)).mappings().all()

    def tipos(v):
        return [o.get('tipo') for o in _json(v, []) if isinstance(o, dict)]

    usuarios_ = dict(nombres)
    usuarios_[0] = 'Sin asignar'
    return jsonify({
        'leads': [{
            'id': r['id'], 'nombre': r['nombre'], 'creado': _dt(r['creado_en']), 'estado': r['estado'],
            'contactado': _dt(r['contactado_en']), 'canal': r['canal_contacto'], 'usuario': r['asignado_a'] or 0,
            'sector': r['nicho'] or '—', 'ciudad': r['ciudad'] or '—', 'prioridad': r['prioridad'] or 'baja',
            'score': r['score'] or 0, 'ticket': r['ticket'], 'oportunidades': tipos(r['oportunidades']),
            'plantilla': r['plantilla'] or '', 'email': bool(r['email']), 'rating': r['rating'],
            'resenas': r['resenas'], 'seguimiento': _iso(r['proximo_seguimiento'])} for r in leads_],
        'eventos': [{'lead': e.lead_id, 'estado': e.estado, 'fecha': _dt(e.fecha), 'usuario': e.usuario_id or 0,
                     'canal': e.canal} for e in eventos],
        'consumo': [{'fecha': _dt(c['fecha']), 'tipo': c['tipo'], 'creditos': c['creditos'],
                     'ahorrados': c['ahorrados'], 'usuario': c['usuario_id'] or 0,
                     'ciudad': c['ciudad'] or '—', 'sector': c['sector'] or '—'} for c in consumo_],
        'usuarios': {str(k): v for k, v in usuarios_.items()},
        'config': {'cuota_mes': CUOTA_MES, 'hoy': date.today().isoformat()},
        'yo': {'id': request.user['id'], 'rol': request.user['rol']},
    })


# ---------------------------------------------------------------- Vistas guardadas

PRESETS_VISTA = {'mes', 'mesant', '3m', '6m', '12m', 'todo', 'custom'}
LISTAS_VISTA = ('ciudad', 'sector', 'usuario', 'prioridad', 'oportunidad')
MAX_VISTAS_POR_USUARIO = 30


def _filtros_validos(d):
    """Devuelve los filtros normalizados o None si no tienen la forma esperada (nunca se guarda
    nada que el panel no pueda interpretar)."""
    if not isinstance(d, dict) or d.get('preset') not in PRESETS_VISTA:
        return None
    out = {'preset': d['preset']}
    for k in ('desde', 'hasta'):
        v = d.get(k)
        if v in (None, ''):
            out[k] = None
        elif isinstance(v, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
            try:
                date.fromisoformat(v)
            except ValueError:
                return None
            out[k] = v
        else:
            return None
    if out['preset'] != 'custom':
        out['desde'] = out['hasta'] = None
    for k in LISTAS_VISTA:
        v = d.get(k, [])
        if not isinstance(v, list) or len(v) > 50 or not all(isinstance(x, str) for x in v):
            return None
        out[k] = [x[:120] for x in v]
    sc = d.get('score')
    if sc is None:
        out['score'] = None
    elif (isinstance(sc, list) and len(sc) == 2 and all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 100 for x in sc)
          and sc[0] <= sc[1]):
        out['score'] = sc
    else:
        return None
    ui = d.get('ui') if isinstance(d.get('ui'), dict) else {}
    out['ui'] = {
        'consumoModo': ui.get('consumoModo') if ui.get('consumoModo') in ('mes', 'dia') else 'mes',
        'heat': ui.get('heat') if ui.get('heat') in ('leads', 'tasa', 'creditos') else 'leads',
        'rend': ui.get('rend') if ui.get('rend') in ('usuario', 'canal', 'sector') else 'usuario',
    }
    return out


def _vista_dict(r, nombres, yo):
    propia = r['usuario_id'] == yo['id']
    return {'id': r['id'], 'nombre': r['nombre'], 'filtros': _json(r['filtros'], {}), 'compartida': bool(r['compartida']),
            'predeterminada': bool(r['predeterminada']) and propia, 'propia': propia,
            'autor': nombres.get(r['usuario_id'], '—'), 'puede_borrar': propia or yo['rol'] == 'admin'}


@app.route('/api/vistas')
def listar_vistas():
    V = db.vistas
    with db.engine.connect() as conn:
        nombres = _nombres_usuarios(conn)
        rows = conn.execute(select(V).where(or_(V.c.usuario_id == request.user['id'], V.c.compartida.is_(True)))
                            .order_by(V.c.nombre)).mappings().all()
    return jsonify({'vistas': [_vista_dict(r, nombres, request.user) for r in rows]})


@app.route('/api/vistas', methods=['POST'])
def crear_vista():
    d = request.get_json(silent=True) or {}
    nombre = re.sub(r'\s+', ' ', str(d.get('nombre') or '')).strip()
    if not nombre or len(nombre) > 60:
        return jsonify({'error': 'El nombre es obligatorio (máximo 60 caracteres)'}), 400
    filtros = _filtros_validos(d.get('filtros'))
    if filtros is None:
        return jsonify({'error': 'Los filtros de la vista no son válidos'}), 400
    V, yo = db.vistas, request.user
    with db.engine.begin() as conn:
        propias = conn.execute(select(V.c.id, V.c.nombre).where(V.c.usuario_id == yo['id'])).all()
        if len(propias) >= MAX_VISTAS_POR_USUARIO:
            return jsonify({'error': f'Máximo {MAX_VISTAS_POR_USUARIO} vistas guardadas: elimina alguna'}), 400
        if any(p.nombre.lower() == nombre.lower() for p in propias):
            return jsonify({'error': 'Ya tienes una vista con ese nombre'}), 409
        nueva = conn.execute(insert(V).values(
            usuario_id=yo['id'], nombre=nombre, filtros=json.dumps(filtros, ensure_ascii=False),
            compartida=bool(d.get('compartida')), predeterminada=False, creado_en=db.ahora())).inserted_primary_key[0]
        r = conn.execute(select(V).where(V.c.id == nueva)).mappings().first()
        nombres = _nombres_usuarios(conn)
    return jsonify(_vista_dict(r, nombres, yo)), 201


@app.route('/api/vistas/<int:vista_id>', methods=['PATCH'])
def editar_vista(vista_id):
    """Solo su autor puede cambiarla: marcarla como predeterminada (una por usuario) o compartirla."""
    d = request.get_json(silent=True) or {}
    V, yo = db.vistas, request.user
    with db.engine.begin() as conn:
        r = conn.execute(select(V).where(V.c.id == vista_id)).mappings().first()
        if not r:
            return jsonify({'error': 'Vista no encontrada'}), 404
        if r['usuario_id'] != yo['id']:
            if not r['compartida']:
                return jsonify({'error': 'Vista no encontrada'}), 404
            return jsonify({'error': 'Solo su autor puede modificar la vista'}), 403
        cambios = {}
        if 'compartida' in d:
            cambios['compartida'] = bool(d['compartida'])
        if 'predeterminada' in d:
            if d['predeterminada']:
                conn.execute(update(V).where(V.c.usuario_id == yo['id']).values(predeterminada=False))
            cambios['predeterminada'] = bool(d['predeterminada'])
        if not cambios:
            return jsonify({'error': 'Nada que actualizar'}), 400
        conn.execute(update(V).where(V.c.id == vista_id).values(**cambios))
        r = conn.execute(select(V).where(V.c.id == vista_id)).mappings().first()
        nombres = _nombres_usuarios(conn)
    return jsonify(_vista_dict(r, nombres, yo))


@app.route('/api/vistas/<int:vista_id>', methods=['DELETE'])
def borrar_vista(vista_id):
    V, yo = db.vistas, request.user
    with db.engine.begin() as conn:
        r = conn.execute(select(V).where(V.c.id == vista_id)).mappings().first()
        if not r:
            return jsonify({'error': 'Vista no encontrada'}), 404
        if r['usuario_id'] != yo['id'] and yo['rol'] != 'admin':
            if not r['compartida']:
                return jsonify({'error': 'Vista no encontrada'}), 404
            return jsonify({'error': 'Solo su autor o un administrador puede eliminarla'}), 403
        conn.execute(db.vistas.delete().where(V.c.id == vista_id))
    return jsonify({'ok': True})


@app.route('/api/serpapi/cuenta')
def serpapi_cuenta():
    """Estado real de la cuenta de SerpAPI. Su API de cuenta no consume créditos; se cachea 5 minutos."""
    if time.time() - _cuenta['t'] < 300 and _cuenta['d'] is not None:
        return jsonify(_cuenta['d'])
    key = os.environ.get('SERPAPI_KEY', '')
    if not key or key == 'tu_api_key_aqui':
        return jsonify({'disponible': False, 'motivo': 'SERPAPI_KEY no configurada'})
    try:
        r = requests.get('https://serpapi.com/account', params={'api_key': key}, timeout=10)
        r.raise_for_status()
        d = r.json()
        out = {'disponible': True, 'plan': d.get('plan_name'), 'cuota': d.get('searches_per_month'),
               'usadas': d.get('this_month_usage'), 'restantes': d.get('total_searches_left')}
    except (requests.RequestException, ValueError):
        # No se devuelve el texto del error: incluiría la URL con la clave
        out = {'disponible': False, 'motivo': 'No se pudo consultar la cuenta de SerpAPI'}
    _cuenta.update(t=time.time(), d=out)
    return jsonify(out)


@app.route('/api/consumo.csv')
def exportar_consumo():
    with db.engine.connect() as conn:
        nombres = _nombres_usuarios(conn)
        rows = conn.execute(select(db.consumo).order_by(db.consumo.c.id)).mappings().all()

    def seguro(v):
        v = '' if v is None else str(v)
        return "'" + v if v[:1] in ('=', '+', '-', '@', '\t', '\r') else v

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Fecha (UTC)', 'Tipo', 'Créditos usados', 'Créditos ahorrados (caché)', 'Usuario', 'Ciudad',
                'Sector', 'Detalle'])
    for r in rows:
        w.writerow([seguro(x) for x in (_dt(r['fecha']), r['tipo'], r['creditos'], r['ahorrados'],
                                        nombres.get(r['usuario_id'], ''), r['ciudad'], r['sector'], r['detalle'])])
    return Response('\ufeff' + buf.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=consumo_serpapi.csv'})


# ---------------------------------------------------------------- Usuarios

@app.route('/api/usuarios')
def listar_usuarios():
    """Cualquier usuario ve la lista (para asignar leads); solo datos básicos."""
    with db.engine.connect() as conn:
        rows = conn.execute(select(db.usuarios).order_by(db.usuarios.c.nombre)).mappings().all()
    return jsonify({'usuarios': [{'id': r['id'], 'usuario': r['usuario'], 'nombre': r['nombre'],
                                  'rol': r['rol'], 'activo': r['activo']} for r in rows]})


@app.route('/api/usuarios', methods=['POST'])
@solo_admin
def crear_usuario():
    d = request.get_json(silent=True) or {}
    usuario = (d.get('usuario') or '').strip().lower()
    nombre = (d.get('nombre') or '').strip()
    password = d.get('password') or ''
    rol = d.get('rol', 'usuario')
    if not usuario or not nombre:
        return jsonify({'error': 'Usuario y nombre son obligatorios'}), 400
    if not usuario.replace('_', '').replace('.', '').replace('-', '').isalnum() or len(usuario) > 60:
        return jsonify({'error': 'El usuario solo admite letras, números, punto, guion y guion bajo'}), 400
    if len(password) < 8:
        return jsonify({'error': 'La contraseña debe tener al menos 8 caracteres'}), 400
    if rol not in db.ROLES:
        return jsonify({'error': 'Rol no válido'}), 400
    try:
        with db.engine.begin() as conn:
            conn.execute(insert(db.usuarios).values(
                usuario=usuario, nombre=nombre[:120], password_hash=generate_password_hash(password),
                rol=rol, activo=True, creado_en=db.ahora()))
    except IntegrityError:
        return jsonify({'error': 'Ese usuario ya existe'}), 409
    return jsonify({'ok': True}), 201


@app.route('/api/usuarios/<int:uid>', methods=['PATCH'])
@solo_admin
def editar_usuario(uid):
    d = request.get_json(silent=True) or {}
    cambios = {}
    if 'activo' in d:
        cambios['activo'] = bool(d['activo'])
    if 'rol' in d:
        if d['rol'] not in db.ROLES:
            return jsonify({'error': 'Rol no válido'}), 400
        cambios['rol'] = d['rol']
    if d.get('password'):
        if len(d['password']) < 8:
            return jsonify({'error': 'La contraseña debe tener al menos 8 caracteres'}), 400
        cambios['password_hash'] = generate_password_hash(d['password'])
    if uid == request.user['id'] and (cambios.get('activo') is False or cambios.get('rol') == 'usuario'):
        return jsonify({'error': 'No puedes desactivarte ni quitarte el rol de administrador'}), 400
    if not cambios:
        return jsonify({'error': 'Nada que actualizar'}), 400
    with db.engine.begin() as conn:
        res = conn.execute(update(db.usuarios).where(db.usuarios.c.id == uid).values(**cambios))
        if not res.rowcount:
            return jsonify({'error': 'Usuario no encontrado'}), 404
    return jsonify({'ok': True})


if __name__ == '__main__':
    # Solo se usa en desarrollo local (python app.py). En producción (Render)
    # gunicorn importa `app` directamente y este bloque no se ejecuta.
    puerto = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=puerto)
