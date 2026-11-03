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

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, MetaData, String, Table, Text,
    create_engine, select, insert, update, func,
)
from werkzeug.security import generate_password_hash

ESTADOS = ['nuevo', 'contactado', 'respondio', 'reunion', 'cerrado', 'descartado']
CANALES = ['whatsapp', 'email', 'telefono']
ROLES = ['admin', 'usuario']


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
)


def init_db():
    metadata.create_all(engine)
    _crear_admin_inicial()


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
