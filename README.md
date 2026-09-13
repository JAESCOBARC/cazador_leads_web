# 🎯 Cazador Leads Web — Prospección Automatizada B2B

Automatización que identifica negocios sin página web, extrae contactos y genera emails personalizados para venta de desarrollo web.

## 📋 Estructura

```
cazador_leads_web/
├── Localización.txt              ← Ciudad/zona donde buscar (ej: "Pereira")
├── nicho.txt                     ← Tipo de negocio (ej: "clínicas veterinarias")
├── cazador_leads.py              ← Script principal de prospección
├── email_template.py             ← Plantilla de emails personalizados
├── prospects_encontrados.md      ← Output con negocios sin web
├── CLAUDE.md                     ← Instrucciones del proyecto
└── README.md                     ← Este archivo
```

## 🔄 Flujo de Automatización

### Input
1. **Localización.txt**: Nombre de ciudad/zona
2. **nicho.txt**: Sector de negocio

### Procesamiento
1. Busca en Google: "[nicho] en [localización]"
2. Accede a Google Maps para extraer datos
3. Filtra: negocios SIN página web
4. Valida: confirma ausencia de web en resultados de búsqueda
5. Extrae: nombre, teléfono, email (si está disponible)

### Output
- **prospects_encontrados.md**: Lista de leads con emails personalizados listos para enviar

## ⚙️ Requisitos

- Python 3.8+
- Librerías:
  ```bash
  pip install requests beautifulsoup4 google-search-results selenium
  ```

- (Opcional) APIs:
  - **SerpAPI** (recomendado): https://serpapi.com (100 búsquedas gratis/mes)
  - **Google Custom Search**: Gratuito hasta 100 búsquedas/día

## 🚀 Uso

```bash
python cazador_leads.py
```

## 📊 Ejemplo de Output

```markdown
## Lead 1: Veterinaria San José
**Teléfono:** +57 300 123 4567
**Email:** contacto@sanjosef.com
**Ubicación:** Pereira, Risaralda
**Estado Web:** NO TIENE
**Ángulo:** Única veterinaria en zona sin presencia digital

### Email
Asunto: San José, ¿por qué no aparecen en Google?
...
```

## 💡 Diferencias con "Personalizador de Emails Fríos"

| Aspecto | EmailsPersonalizador | Cazador Leads Web |
|--------|-------------------|------------------|
| Objetivo | Vender servicios marketing | Vender desarrollo web |
| Input | URLs de competencia | Búsqueda en Google Maps |
| Filtro | Stack técnico | Presencia web (SÍ/NO) |
| Output | Emails por tracking | Emails sin web |

## 🔐 Notas de Seguridad

- No reutilizar emails generados sin verificación manual
- Validar teléfonos antes de contactar
- Respetar GDPR/CCPA (no usar en EU sin consentimiento)
- Rate limiting: máx 10 búsquedas por minuto
