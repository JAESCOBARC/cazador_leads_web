# 📊 Status — Cazador Leads Web

**Última actualización:** 21 de noviembre de 2026
**Estado:** funcional. App web (Flask) con Radar de oportunidades, leads, analítica y usuarios.

## Qué hace hoy
- **Radar:** escanea ciudad + sectores en Google Maps (SerpAPI) con paginación, cuadrícula de barrios y caché de consultas.
- **Escáner de oportunidades** (`escaner.py`): sin web, web débil, sin medición para Ads, web que no capta, SEO local, reputación y app de gestión (hipótesis). Ver tabla en `CLAUDE.md`.
- **Email y WhatsApp** leídos de la web del negocio (portada, contacto, aviso legal), con su fuente; nunca inventados.
- **Instagram/Facebook:** lectura gratuita de la bio del perfil enlazado en Maps y búsqueda opcional en Google por lead (1 crédito) para email/WhatsApp/teléfono publicados; botón «Perfil» para verificar.
- **Mapa:** se mueve a la ciudad escrita antes de escanear.
- **Score y prioridad** por lead; ticket estimado por sector; mapa con puntos por prioridad.
- **Mensajes** (`mensajes.py`) con datos reales de Maps, un servicio por mensaje, ≤150 palabras, variantes A/B y secuencia de seguimiento (día 0, +3, +4).
- **Analítica** por canal, nicho, ciudad, usuario, tipo de oportunidad, prioridad y plantilla.
- Login con roles, asignación de leads, historial de contactos, exportación CSV.

## Configuración clave (`.env` / Render)
`SERPAPI_KEY`, `DATABASE_URL`, `SECRET_KEY`, `ADMIN_*`, `REMITENTE_*`, `AGENCIA_NOMBRE`, `MAX_RESULTS`, `MAX_SCAN_WEBS`, `CASO_EXITO`. Ver `.env.example`.

## Notas
- Render: `gunicorn --workers 1 --threads 4 --timeout 120` (los trabajos del radar y el límite de intentos de login viven en memoria; con un solo worker son consistentes).
- Créditos SerpAPI: 1 por página de Maps. Cobertura rápida = 1, normal = 2, profunda = 10 por sector. Las consultas repetidas usan caché (7 días).
- Las webs se leen con peticiones HTTP normales (sin gastar créditos), con protección contra SSRF.

## Pendiente / ideas
- Búsqueda de redes en lote para los leads de prioridad alta (hoy es lead a lead para controlar créditos).
- PageSpeed Insights (API gratuita) para medir velocidad móvil real.
- Mockup/demo de web para los leads de prioridad alta.
- Envío automatizado (Klaviyo): sigue en pausa por la regla de verificación manual.
