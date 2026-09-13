# Cazador Leads Web — Instrucciones del Proyecto

## Objetivo

Automatizar la prospección de negocios sin página web en un sector y localización específicos. Extraer contactos y generar emails personalizados para venta de desarrollo web.

## Tono de los Emails

Idéntico al proyecto **Personalizador de Emails Fríos**:
- Directo, peer-to-peer, sin florituras
- Tuteo siempre
- Primera persona conversacional: "vi que no aparecen", "encontré que"
- Nunca impersonal: "se detectó", "no aparecieron"
- Un único servicio por email: desarrollo web
- Máximo 150 palabras en cuerpo
- Sin hipérboles ni jerga de agencia

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
