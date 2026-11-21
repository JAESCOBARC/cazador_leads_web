# -*- coding: utf-8 -*-
"""
Capa de datos: usuarios, leads y registro de contactos.

Usa Postgres si existe DATABASE_URL (Render/Neon/Supabase); si no, SQLite local
(solo para desarrollo: en Render gratis el disco se borra en cada redeploy).
"""

import os
import re
import secrets
from datetime import datetime, timezone

from datetime import timedelta

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, MetaData, String, Table, Text,
    create_engine, inspect, select, insert, update, delete, func, text,
)
from werkzeug.security import generate_password_hash

ESTADOS = ['nuevo', 'contactado', 'respondio', 'reunion', 'cerrado', 'descartado']
CANALES = ['whatsapp', 'email', 'telefono']
ROLES = ['admin', 'usuario']
PRIORIDADES = ['alta', 'media', 'baja']


def _url():
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        return 'sqlite:///cazador_leads.db'
    # Render/Heroku entregan "postgres://", SQLAlchemy exige "postgresql://"
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


engine = create_engine(_url(), pool_pre_ping=True, future=True)
metadata = MetaData()


def ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


usuarios = Table(
    'usuarios', metadata,
    Column('id', Integer, primary_key=True),
    Column('usuario', String(60), nullable=False, unique=True),
    Column('nombre', String(120), nullable=False),
    Column('password_hash', String(255), nullable=False),
    Column('rol', String(20), nullable=False, default='usuario'),
    Column('activo', Boolean, nullable=False, default=True),
    Column('creado_en', DateTime, nullable=False, default=ahora),
)

leads = Table(
    'leads', metadata,
    Column('id', Integer, primary_key=True),
    Column('clave', String(255), nullable=False, unique=True),  # evita duplicados
    Column('nombre', String(255), nullable=False),
    Column('telefono', String(60)),
    Column('email', String(255)),
    Column('whatsapp', String(500)),
    Column('redes_sociales', String(500)),
    Column('direccion', String(500)),
    Column('nicho', String(120)),
    Column('ciudad', String(120)),
    Column('pais', String(120)),
    Column('canal_recomendado', String(20)),
    Column('asunto', Text),
    Column('cuerpo', Text),
    Column('estado', String(20), nullable=False, default='nuevo'),
    Column('canal_contacto', String(20)),
    Column('asignado_a', Integer, ForeignKey('usuarios.id')),
    Column('contactado_en', DateTime),
    Column('proximo_seguimiento', Date),
    Column('notas', Text),
    Column('creado_en', DateTime, nullable=False, default=ahora),
    Column('actualizado_en', DateTime, nullable=False, default=ahora),
    # --- Radar: datos reales de Maps + diagnóstico de oportunidades ---
    Column('rating', Float),
    Column('resenas', Integer),
    Column('tipo', String(160)),
    Column('lat', Float),
    Column('lon', Float),
    Column('web_url', String(500)),
    Column('tiene_web', Boolean),
    Column('maps_url', String(500)),
    Column('score', Integer),
    Column('prioridad', String(10)),
    Column('ticket', String(10)),
    Column('competidores', Integer),
    Column('oportunidades', Text),   # JSON: lista de oportunidades detectadas
    Column('diagnostico', Text),     # JSON: detalle del escaneo
    Column('plantilla', String(60)),  # angulo:canal:variante del mensaje generado
    Column('escaneado_en', DateTime),
)

contactos = Table(
    'contactos', metadata,
    Column('id', Integer, primary_key=True),
    Column('lead_id', Integer, ForeignKey('leads.id', ondelete='CASCADE'), nullable=False),
    Column('usuario_id', Integer, ForeignKey('usuarios.id')),
    Column('estado', String(20), nullable=False),
    Column('canal', String(20)),
    Column('nota', Text),
    Column('fecha', DateTime, nullable=False, default=ahora),
    Column('plantilla', String(60)),
)

# Respuestas de SerpAPI ya consultadas: evita gastar créditos repitiendo la misma búsqueda.
cache_busqueda = Table(
    'cache_busqueda', metadata,
    Column('clave', String(255), primary_key=True),
    Column('datos', Text, nullable=False),
    Column('creado_en', DateTime, nullable=False, default=ahora),
)


# Créditos de SerpAPI consumidos por esta app (y los ahorrados gracias a la caché), para el panel mensual.
consumo = Table(
    'consumo', metadata,
    Column('id', Integer, primary_key=True),
    Column('fecha', DateTime, nullable=False, default=ahora),
    Column('tipo', String(20), nullable=False),          # radar | redes
    Column('creditos', Integer, nullable=False, default=0),
    Column('ahorrados', Integer, nullable=False, default=0),
    Column('usuario_id', Integer, ForeignKey('usuarios.id')),
    Column('ciudad', String(120)),
    Column('sector', String(120)),
    Column('lead_id', Integer),
    Column('detalle', String(255)),
)


# Vistas guardadas del panel analítico: los filtros (JSON validado) con un nombre.
vistas = Table(
    'vistas', metadata,
    Column('id', Integer, primary_key=True),
    Column('usuario_id', Integer, ForeignKey('usuarios.id'), nullable=False),
    Column('nombre', String(60), nullable=False),
    Column('filtros', Text, nullable=False),
    Column('compartida', Boolean, nullable=False, default=False),
    Column('predeterminada', Boolean, nullable=False, default=False),
    Column('creado_en', DateTime, nullable=False, default=ahora),
)


# Una fila por umbral y mes ya avisado (evita repetir el correo de cuota).
alertas_enviadas = Table(
    'alertas_enviadas', metadata,
    Column('clave', String(40), primary_key=True),   # "2026-11:80"
    Column('umbral', Integer),
    Column('enviada_en', DateTime, nullable=False, default=ahora),
    Column('usados', Integer),
    Column('cuota', Integer),
)

# Registro de los correos enviados a leads desde la app (auditoría y límite diario).
envios = Table(
    'envios', metadata,
    Column('id', Integer, primary_key=True),
    Column('lead_id', Integer, nullable=False),
    Column('usuario_id', Integer, ForeignKey('usuarios.id')),
    Column('destino', String(255), nullable=False),
    Column('asunto', String(255)),
    Column('estado', String(20), nullable=False),    # enviado | error
    Column('error', String(255)),
    Column('cuerpo', Text),                           # texto enviado (sin la línea de baja)
    Column('fecha', DateTime, nullable=False, default=ahora),
)


# Ajustes gestionados desde la app (las claves se guardan cifradas; ver ajustes.py).
ajustes = Table(
    'ajustes', metadata,
    Column('clave', String(60), primary_key=True),
    Column('valor', Text, nullable=False),
    Column('secreto', Boolean, nullable=False, default=False),
    Column('actualizado_en', DateTime, nullable=False, default=ahora),
    Column('actualizado_por', Integer, ForeignKey('usuarios.id')),
)


def registrar_consumo(tipo, creditos, ahorrados=0, usuario_id=None, ciudad=None, sector=None,
                      lead_id=None, detalle=None):
    """Anota un consumo. Nunca debe romper la operación principal si falla."""
    if not creditos and not ahorrados:
        return
    try:
        with engine.begin() as conn:
            conn.execute(insert(consumo).values(
                fecha=ahora(), tipo=tipo, creditos=int(creditos or 0), ahorrados=int(ahorrados or 0),
                usuario_id=usuario_id, ciudad=(ciudad or '')[:120], sector=(sector or '')[:120],
                lead_id=lead_id, detalle=(detalle or '')[:255]))
    except Exception as e:  # noqa: BLE001
        print(f"[CONSUMO] No se pudo registrar: {e}")
        return
    import alertas  # import tardío: evita el ciclo db <-> alertas
    alertas.revisar()  # avisa por email si se cruzó el umbral de cuota (nunca lanza)


def init_db():
    metadata.create_all(engine)
    _migrar()
    _crear_admin_inicial()


def _migrar():
    """create_all no añade columnas a tablas existentes: las añade aquí (ALTER TABLE
    ADD COLUMN, nullable) para no perder los leads ya guardados."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for tabla in metadata.sorted_tables:
            if not insp.has_table(tabla.name):
                continue
            existentes = {c['name'] for c in insp.get_columns(tabla.name)}
            for col in tabla.columns:
                if col.name not in existentes and col.nullable:
                    tipo = col.type.compile(engine.dialect)
                    conn.execute(text(f'ALTER TABLE {tabla.name} ADD COLUMN {col.name} {tipo}'))


def cache_get(clave, ttl_dias=7):
    with engine.connect() as conn:
        row = conn.execute(select(cache_busqueda).where(cache_busqueda.c.clave == clave)).mappings().first()
    if not row or row['creado_en'] < ahora() - timedelta(days=ttl_dias):
        return None
    return row['datos']


def cache_set(clave, datos):
    with engine.begin() as conn:
        conn.execute(delete(cache_busqueda).where(cache_busqueda.c.clave == clave))
        conn.execute(insert(cache_busqueda).values(clave=clave, datos=datos, creado_en=ahora()))


def _crear_admin_inicial():
    """Crea el primer administrador si no hay usuarios. Credenciales por env
    (ADMIN_USER / ADMIN_PASSWORD); si falta la clave se genera una y se imprime
    una sola vez en el log."""
    with engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(usuarios)).scalar():
            return
        user = os.environ.get('ADMIN_USER', 'admin').strip() or 'admin'
        password = os.environ.get('ADMIN_PASSWORD', '').strip()
        generada = not password
        if generada:
            password = secrets.token_urlsafe(12)
        conn.execute(insert(usuarios).values(
            usuario=user.lower(), nombre='Administrador',
            password_hash=generate_password_hash(password), rol='admin', activo=True,
        ))
    if generada:
        print(f"[AUTH] Administrador creado. Usuario: {user.lower()}  Contraseña temporal: {password}")
    else:
        print(f"[AUTH] Administrador '{user.lower()}' creado desde variables de entorno.")


def clave_lead(nombre, telefono, ciudad):
    """Clave de deduplicación: el teléfono (solo dígitos) o, si no hay, nombre+ciudad."""
    digitos = re.sub(r'\D', '', telefono or '')
    if len(digitos) >= 7:
        return 'tel:' + digitos
    base = re.sub(r'\s+', ' ', (nombre or '').strip().lower())
    return f"nom:{base}|{(ciudad or '').strip().lower()}"
