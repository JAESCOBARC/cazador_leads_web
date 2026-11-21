# Cazador Leads Web — Instrucciones del Proyecto

## Objetivo

Automatizar la prospección de negocios sin página web en un sector y localización específicos. Extraer contactos y generar emails personalizados para venta de desarrollo web.

## Tono de los Emails

Idéntico al proyecto **Personalizador de Emails Fríos**:
- Directo, peer-to-peer, sin florituras
- Tuteo siempre
- Primera persona conversacional: "vi que no aparecen", "encontré que"
- Nunca impersonal: "se detectó", "no aparecieron"
- Un único servicio por mensaje, elegido según la oportunidad principal del negocio (desarrollo web, medición para Ads, SEO local, app de facturación y gastos, reseñas)
- Máximo 150 palabras en cuerpo
- Sin hipérboles ni jerga de agencia

## Radar de oportunidades (versión web)

La app web escanea una ciudad por sectores y detecta qué le falta a cada negocio (`escaner.py`):

| Oportunidad | Cómo se detecta | ¿Verificada? |
|---|---|---|
| Sin web | Maps no lista web propia (solo redes, WhatsApp o directorio) | Sí |
| Web débil | Sin HTTPS, sin adaptación a móvil, lenta o `business.site` | Sí (si no responde: "por confirmar") |
| Sin medición Ads | La web no tiene Analytics, píxel de Meta, Google Ads ni Tag Manager | Sí; no se afirma si la web es solo JavaScript o bloquea el escaneo |
| La web no capta | Sin formulario, teléfono ni WhatsApp visibles | Sí |
| SEO local débil | Pocas reseñas, sin horario, sin datos estructurados, título sin ciudad, sin mapa | Sí |
| Reputación | Rating < 4,2 con reseñas | Sí |
| App de gestión | **Hipótesis** por tipo de negocio; se confirma en la primera conversación | No |

**Contactos:** Google Maps (SerpAPI) solo da teléfono y web; nunca email. El email y el WhatsApp se leen de la web del propio negocio (portada y, si falta alguno, contacto / aviso legal / privacidad), solo si están publicados: `mailto:`, texto visible, emails ofuscados, protección de Cloudflare, datos estructurados y enlaces `wa.me`. Nunca se adivinan (`info@dominio`). Canal recomendado: WhatsApp publicado > email real > teléfono (WhatsApp sin confirmar). Cada dato guarda su fuente. **Instagram y Facebook** (`redes.py`): una petición automática a un perfil no devuelve email, teléfono ni WhatsApp (Instagram solo entrega JavaScript; Facebook, un fragmento de la bio). Hay tres vías: (1) el radar lee gratis la bio pública del perfil que el negocio enlazó en Maps; (2) en el modal del lead, el botón «Buscar en Instagram/Facebook» consulta Google (1 crédito, con caché) y recoge lo que la bio publica, también para negocios sin web; (3) botón «Perfil» para verificar a mano. Solo perfiles públicos, sin iniciar sesión, sin rastrear seguidores; se filtran homónimos por nombre y siempre hay que confirmar que el perfil es del negocio.

**Panel analítico** (pestaña Analítica, `static/analitica.js`): estilo cuadro de mando con ECharts. El consumo de créditos de SerpAPI se registra por evento en la tabla `consumo` (radar y búsqueda de redes, con los créditos ahorrados por caché), por usuario, ciudad y sector; el panel lo muestra mes a mes con la cuota (`SERPAPI_CUOTA_MES` o el dato real de la API de cuenta de SerpAPI, que no gasta créditos), proyección a fin de mes y eficiencia (créditos por lead, por lead con email, por respuesta). Todo se recalcula en el navegador: filtros de fecha/ciudad/sector/usuario/prioridad/oportunidad y clic en cualquier gráfico (filtros cruzados), arrastre sobre la actividad semanal para filtrar fechas, tooltips y vista de tabla en cada gráfico. **Vistas guardadas:** en la barra de filtros se guardan los filtros actuales con un nombre (rango relativo o fechas fijas, ciudad, sector, usuario, prioridad, oportunidad, puntuación y la forma de los gráficos). Cada usuario tiene hasta 30; pueden compartirse con el equipo (los demás las ven y aplican, no las modifican; un admin puede eliminarlas) y una por usuario puede ser la predeterminada: el panel se abre con ella. Los filtros se validan en el servidor antes de guardarse. Solo se registra el consumo desde que existe esta versión. Colores validados con el validador de paleta (categórico azul/naranja/aqua, prioridad rosa/ámbar/violeta, ordinal azul); solo modo claro, porque la app no tiene modo oscuro.

**Correo** (`correo.py`, `alertas.py`; guía en `SETUP_CORREO.md`): la app envía por SMTP (tu Gmail con contraseña de aplicación) o por la API de Resend; las credenciales solo van en variables de entorno. (1) **Aviso de cuota**: un correo al llegar al 80 % (`ALERTA_UMBRALES`) de las búsquedas de SerpAPI, una vez por mes y umbral, tomando lo mayor entre lo que registró la app y lo que informa la cuenta real; si el envío falla se reintenta sin marcarlo como enviado. (2) **Propuestas a clientes**: botón «Enviar por email» en el lead, siempre manual (regla de este proyecto: nunca enviar sin verificación manual): vista previa editable y confirmación, solo al email que el propio negocio publicó, tope diario (`ENVIO_MAX_DIA`, por defecto 5), una vez cada 24 h por lead, firma y línea de baja, bloqueo si quedan datos sin completar ([TU NOMBRE]…), registro de cada intento y el lead pasa a *Contactado*. La app no lee las respuestas: si un cliente dice que no, hay que marcarlo a mano como *Descartado* (y entonces ya no se le ofrece el envío).

**Sin IA:** nada de la app usa modelos de IA (ni Claude ni otros): los mensajes son plantillas con datos reales, y la detección y la puntuación son reglas. El único coste son los créditos de SerpAPI.

**Lote de redes** (Mis leads → «Buscar redes en lote»): consulta Instagram/Facebook vía Google de los leads *nuevos sin email*, de mayor a menor puntuación, con prioridad y tope de créditos elegidos por ti (máximo `LOTE_MAX_CREDITOS`). Las consultas en caché no cuestan; se detiene al llegar al tope o tras 3 errores seguidos. Los datos se guardan con su fuente y hay que verificarlos antes de enviar.

**Mapa 3D** (MapLibre + OpenFreeMap, sin clave): inclinado y con órbita durante el escaneo, flechas ◀ ▶ ▲ ▼ para girar e inclinar, pines en forma de flecha con la puntuación y columnas de altura proporcional al score (rosa = alta, ámbar = media, azul pizarra = baja).

Cada lead recibe un score (demanda en Maps + oportunidades + alcanzabilidad + ticket del sector) y prioridad alta/media/baja.
El ticket por sector es una estimación orientativa. El mini-caso solo aparece si defines `CASO_EXITO` (un caso real).
Seguimiento: mensaje inicial → +3 días → +4 días → cierre. Cada plantilla (ángulo:canal:variante A/B) se mide en Analítica.
Tests: `pytest tests` (offline, sin gastar créditos).

## Flujo de Ejecución

### 1️⃣ Input
- **Localización.txt**: Nombre de ciudad/zona (ej: "Pereira", "Lima Cercado", "Bogotá")
- **nicho.txt**: Tipo de negocio (ej: "clínicas veterinarias", "salones de belleza", "farmacias")

### 2️⃣ Búsqueda en Google
Simular búsqueda: `[nicho] en [localización]`
Ejemplo: `clínicas veterinarias en Pereira`

### 3️⃣ Filtrado: Negocios SIN Web
- Extraer resultados de Google Search
- Verificar si aparecen con página web
- Extraer SOLO los que NO tengan web detectada
- Validar cruzando en Google Maps

### 4️⃣ Extracción de Contactos
Para cada negocio sin web:
- **Nombre** del negocio
- **Teléfono** (primario)
- **Email** (si está disponible en Maps/búsqueda)
- **Ubicación exacta** (dirección, barrio)

### 5️⃣ Análisis del Problema
Antes de escribir cada email, evaluar:
- ¿Aparecen en Google Maps pero sin web?
- ¿Tienen competidores en la zona con web?
- ¿Qué dolor específico tiene (no aparecer en búsquedas, perder clientes)?
- ¿Qué oportunidad hay (cuántos clientes potenciales pierden)?

### 6️⃣ Generación de Emails

- **Si el contacto tiene email**, genera el email personalizado con la siguiente estructura:
Estructura del email:
```
**Asunto:** [Nombre negocio]: problema específico + oportunidad

Hola,

[APERTURA]: cita algo real y específico de lo encontrado
Ejemplo: "vi que aparecen en Google Maps pero sin página web propia"

En [TU AGENCIA] trabajamos con [SECTOR] ayudándoles a [RESULTADO].

Lo hacemos a través de [SERVICIO ÚNICO]: desarrollo web.

[MINI-CASO]: cliente similar en el sector, resultado concreto.

¿Tiene sentido explorar si aplica a vuestro caso?
¿Tienes 20 minutos esta semana?

[TU FIRMA]
```

- **Si el contacto NO tiene email**, genera UN MENSAJE personalizado para enviar por **whatsapp**:

Estructura del whatsapp:
```
*Hola [NOMBRE NEGOCIO]*

Vi que aparecen en Google Maps pero sin página web propia

En [TU AGENCIA] trabajamos con [SECTOR] ayudándoles a [RESULTADO].

Lo hacemos a través de [SERVICIO ÚNICO]: desarrollo web.

[MINI-CASO]: cliente similar en el sector, resultado concreto.

¿Tiene sentido explorar si aplica a su caso?
¿Tienes 20 minutos esta semana?

```
### 7️⃣ Output
**prospects_encontrados.md** con estructura:

```markdown
## Lead [N]: [Nombre negocio]

**Teléfono:** [número]
**Email:** [email o N/A]
**Ubicación:** [dirección/barrio]
**Fuente:** Google Maps + Búsqueda Google
**Estado Web:** NO TIENE

### Análisis
- Aparece en Google Maps: SÍ
- Página web detectada: NO
- Competencia local con web: SÍ (X negocios)
- Oportunidad: Recuperar clientes que buscan en Google

### Email

**Asunto:** [asunto personalizado]

[cuerpo completo]
```

## Ángulos de Venta (Ejemplos)

| Situación | Ángulo | Email |
|-----------|--------|-------|
| Maps sí, web no | Pierden búsquedas | "Vi que aparecen en Maps pero sin web — pierden X clientes que buscan en Google" |
| Competencia local con web | Desventaja competitiva | "Tus competidores [X, Y] tienen web. ¿Qué clientes pierdes cada mes?" |
| Teléfono pero sin contacto | Difícil agendar | "Solo tienen teléfono — un formulario web sumaría X citas más al mes" |
| Sin reviews públicos | Sin prueba social | "Tus competidores tienen reviews en Google — tú no. ¿Eso cierra ventas?" |

## Restricciones

- Máximo 150 palabras en cuerpo del email
- Un único servicio: desarrollo web
- Citar solo datos verificables (encontrados en Maps o búsqueda)
- Sin IDs técnicos en el cuerpo
- Sin jerga: nada de "implementar soluciones", "potenciar resultados"
- Sin hipérboles: nada de "increíble", "revolucionario"

## Herramientas Permitidas

✅ Para búsqueda y extracción:
- Google Custom Search API (100 búsquedas gratis/día)
- SerpAPI (100 búsquedas gratis/mes)
- Google Maps API
- BeautifulSoup + Selenium (web scraping manual)

❌ No permitido:
- Usar datos de bases de datos spam
- Enviar emails sin verificación manual
- Clonar webs de la competencia

## Flujo de Trabajo Recomendado

```
1. Leer Localización.txt y nicho.txt
   ↓
2. Buscar en Google: "[nicho] en [localización]"
   ↓
3. Para cada resultado, revisar:
   - ¿Tiene página web propia?
   - ¿Aparece solo en Maps/Directorios?
   ↓
4. Filtrar: SOLO los SIN web
   ↓
5. Extraer contacto: nombre, teléfono, email
   ↓
6. Analizar: ¿cuál es el problema específico?
   ↓
7. Generar email personalizado
   ↓
8. Guardar en prospects_encontrados.md
```

## Metricas de Éxito

- Mínimo 5 negocios identificados sin web
- Máximo 20 por ejecución
- 100% de emails con datos verificables
- 0 falsos positivos (todos deben estar sin web)
- Email específico por lead (no genérico)

## Actualización
Siempre debes hacer commit y push
cada respuesta que me des debe tener este icono 🤖
