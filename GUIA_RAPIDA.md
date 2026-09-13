# ⚡ Guía Rápida — Cazador Leads Web

## 🎯 ¿Qué hace?

Automatiza la búsqueda de **negocios sin página web** en Google Maps, extrae contactos y genera **emails personalizados** listos para enviar.

**Input:**
- Localización.txt → `Pereira`
- nicho.txt → `clínicas veterinarias`

**Output:**
- prospects_encontrados.md → 4+ leads con emails personalizados

---

## 🚀 Inicio Rápido (5 minutos)

### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 2. Editar archivos de entrada

**Localización.txt:**
```
Lima
```

**nicho.txt:**
```
salones de belleza
```

### 3. Ejecutar
```bash
python cazador_leads.py
```

### 4. Ver resultados
Abrir `prospects_encontrados.md` — los emails están listos.

---

## 📋 Estructura de Archivos

```
cazador_leads_web/
├── Localización.txt           ← EDITAR: Tu ciudad/zona
├── nicho.txt                  ← EDITAR: Tu sector (ej: "clínicas veterinarias")
│
├── cazador_leads.py           ← Script principal (no tocar)
├── requirements.txt           ← Dependencias Python
├── .env.example               ← Plantilla de configuración
│
├── CLAUDE.md                  ← Instrucciones detalladas
├── SETUP_APIS.md              ← Cómo conectar APIs reales
├── GUIA_RAPIDA.md             ← Este archivo
│
└── prospects_encontrados.md   ← OUTPUT (se genera automáticamente)
```

---

## 🔄 Ciclo Completo

```
┌─────────────────────────────────────────────────┐
│ 1. INPUTS                                       │
│    Localización.txt + nicho.txt                 │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ 2. BÚSQUEDA EN GOOGLE                           │
│    "[nicho] en [localización]"                  │
│    (Usando API: SerpAPI, Google Search, Maps)   │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ 3. FILTRADO: SIN PÁGINA WEB                     │
│    Eliminar negocios que sí tienen web          │
│    Mantener solo: SIN web                       │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ 4. EXTRACCIÓN DE CONTACTOS                      │
│    - Nombre del negocio                         │
│    - Teléfono                                   │
│    - Email (si disponible)                      │
│    - Ubicación exacta                           │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ 5. ANÁLISIS DEL PROBLEMA                        │
│    - ¿Qué pierden sin web?                      │
│    - ¿Cuánta competencia local tiene web?       │
│    - ¿Cuál es el ángulo de venta?               │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ 6. GENERACIÓN DE EMAILS                         │
│    - Asunto personalizado                       │
│    - Cuerpo adaptado al negocio                 │
│    - Con mini-caso del sector                   │
│    - Firma profesional                          │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│ 7. OUTPUT: prospects_encontrados.md             │
│    ✓ Lead 1 - Email completo                    │
│    ✓ Lead 2 - Email completo                    │
│    ✓ Lead 3 - Email completo                    │
│    ...                                          │
└─────────────────────────────────────────────────┘
```

---

## 📊 Ejemplo Real: Ejecutión

### Input
```
Localización: Pereira
Nicho: clínicas veterinarias
```

### Proceso
```
🔍 Buscando: 'clínicas veterinarias en Pereira'
✓ Total encontrados: 6 negocios
✓ Con web: 2
✓ SIN web (leads válidos): 4
📧 Generando emails personalizados...
```

### Output
```markdown
## Lead 1: Veterinaria San José

**Teléfono:** +57 300 123 4567
**Email (verificar):** contacto@example.com
**Ubicación:** Calle 50 #20-30, Pereira
**Estado Web:** NO TIENE

### Email

**Asunto:** Veterinaria San José: sin web = clientes que pierden cada mes

Hola,

vi que aparecen en Google Maps pero sin página web propia — mientras otros 
en Pereira sí la tienen.

Dejas que la competencia capte los clientes que te buscan en Google

En CodeAgency trabajamos con clínicas veterinarias ayudándoles a captar más 
clientes desde búsquedas de Google.

Lo hacemos a través de **desarrollo web + SEO**. Una clínicas en Pereira fue 
similar hace 6 meses. Implementó web + WhatsApp integrado — en 3 meses 
sumaron 12-15 citas nuevas mensuales directas de búsquedas de Google.

¿Tiene sentido explorar si aplica a vuestro caso?
¿Tienes 20 minutos esta semana?

Carlos Mendoza
Head of Growth — CodeAgency
carlos@codeagency.pe | +51 999 000 000
```

---

## ⚙️ Configurar con Datos Reales

El script actual usa **datos simulados**. Para usar datos REALES:

### Opción A: SerpAPI (RECOMENDADO - 2 minutos)

1. **Crear cuenta gratis**: https://serpapi.com
2. **Obtener API Key**: Panel → Settings
3. **Crear archivo `.env`**:
   ```
   SERPAPI_KEY=tu_clave_aqui
   ```
4. **Listo** — Script automáticamente usará datos reales

Ver: `SETUP_APIS.md` → Opción 1

### Opción B: Google Custom Search (10 minutos)
- Ver: `SETUP_APIS.md` → Opción 2

### Opción C: Selenium + web scraping (15 minutos)
- Ver: `SETUP_APIS.md` → Opción 3

---

## 🎯 Casos de Uso

| Caso | Localización | Nicho | Leads Esperados |
|------|-------------|-------|----------------|
| Peluquerías sin web | Lima Cercado | salones de belleza | 8-12 |
| Farmacias indie | Bogotá | farmacias independientes | 5-8 |
| Clínicas vet pequeñas | Medellín | veterinarias pequeñas | 6-10 |
| Restaurantes locales | Valparaíso | restaurantes artesanales | 10-15 |
| Consultorios médicos | Santiago | consultorios privados | 4-7 |

---

## 💡 Mejores Ángulos de Venta

**Problema → Solución**

| Problema | Ángulo | Frase Gancho |
|----------|--------|-------------|
| Sin web, solo Maps | Captura búsquedas | "Aparecen en Maps pero pierden clientes que buscan en Google" |
| Competencia tiene web | Desventaja | "Tus 3 competidores en la zona tienen web, ¿qué clientes pierdes?" |
| Solo teléfono | Automatizar | "Un formulario web + chat suma 5-8 citas nuevas/mes" |
| Sin testimonios | Prueba social | "Tus competidores tienen reviews en Google, tú no" |

---

## 🔐 Checklist Antes de Enviar

- [ ] Email verificado (no es generado)
- [ ] Teléfono confirmado (llamar rápido)
- [ ] Negocio realmente sin web
- [ ] Email menos de 150 palabras
- [ ] Máx 3-5 emails por día
- [ ] No enviar a empresas grandes (target: pequeños/medianos)

---

## 🐛 Solución de Problemas

### "ModuleNotFoundError: No module named 'requests'"
```bash
pip install -r requirements.txt
```

### "API key inválida"
```bash
# Verificar archivo .env
# Copiar: cp .env.example .env
# Editar con tu API key correcta
```

### "No encuentra negocios"
1. Verificar spelling en Localización.txt y nicho.txt
2. Usar nombres de ciudades reales (no abreviaciones)
3. Probar en: https://www.google.com/maps

### "Emails no personalizados"
- Datos simulados. Conectar API real (ver SETUP_APIS.md)
- Luego ejecutar de nuevo

---

## 📈 Próximos Pasos

1. ✅ Ejecutar script con datos simulados
2. ✅ Revisar `prospects_encontrados.md`
3. → Conectar SerpAPI (5 min)
4. → Ejecutar con datos reales
5. → Validar emails manualmente
6. → Enviar (máx 5/día, esperar respuestas)

---

## 📞 Soporte

Ver archivos:
- **Más detalles**: CLAUDE.md
- **Configurar APIs**: SETUP_APIS.md
- **Instrucciones originales**: README.md

---

**¡Listo!** Tienes 4+ leads listos para prospectar. 🚀
