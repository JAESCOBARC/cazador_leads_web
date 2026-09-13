# 🔧 Configuración de APIs para Datos Reales

Por defecto, el script usa **datos simulados** para demostración. Para **búsquedas reales**, configura una de estas APIs.

## 📌 Opción 1: SerpAPI (RECOMENDADO)

### ¿Por qué SerpAPI?
- ✅ 100 búsquedas **gratis/mes**
- ✅ Datos directos de Google Search + Google Maps
- ✅ Fácil de integrar
- ✅ Sin límite de tasa después del límite gratis

### Pasos

1. **Registrarse**: https://serpapi.com/users/sign_up
2. **Obtener API Key**: Panel → Settings → API Key
3. **Instalar librería**:
   ```bash
   pip install google-search-results
   ```

4. **Crear archivo `.env`** en la carpeta del proyecto:
   ```
   SERPAPI_KEY=tu_api_key_aqui
   ```

5. **Modificar `cazador_leads.py`** (línea ~100):

```python
def buscar_en_google(self):
    """Busca en Google Maps usando SerpAPI"""
    import os
    from serpapi import Client
    
    # Leer API key
    serpapi_key = os.getenv("SERPAPI_KEY")
    if not serpapi_key:
        print("❌ Variable SERPAPI_KEY no configurada")
        return self._get_mock_results()
    
    client = Client(api_key=serpapi_key)
    
    # Búsqueda en Google Maps
    query = f"{self.nicho} en {self.localizacion}"
    results = client.search({
        "q": query,
        "engine": "google_maps",
        "location": self.localizacion,
        "type": "search"
    })
    
    leads = []
    for result in results.get("local_results", []):
        leads.append({
            "nombre": result.get("title"),
            "telefono": result.get("phone"),
            "email": result.get("email"),  # Si está disponible
            "direccion": result.get("address"),
            "tiene_web": bool(result.get("website")),
            "url": result.get("website"),
            "maps_url": result.get("link")
        })
    
    return leads
```

---

## 📌 Opción 2: Google Custom Search

### ¿Por qué Google Custom Search?
- ✅ 100 búsquedas **gratis/día**
- ✅ Oficial de Google
- ❌ Más complejo de configurar
- ❌ No incluye Google Maps por defecto

### Pasos

1. **Crear motor de búsqueda**:
   - Ir a: https://programmablesearchengine.google.com
   - Crear nuevo motor de búsqueda
   - Obtener **Search Engine ID** y **API Key**

2. **Instalar librería**:
   ```bash
   pip install google-api-python-client
   ```

3. **Modificar `cazador_leads.py`**:

```python
from googleapiclient.discovery import build

def buscar_en_google(self):
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    
    service = build("customsearch", "v1", developerKey=api_key)
    
    result = service.cse().list(
        q=f"{self.nicho} en {self.localizacion}",
        cx=search_engine_id,
        num=10
    ).execute()
    
    # Procesar resultados...
    return leads
```

---

## 📌 Opción 3: Google Maps API + Selenium

Para extraer datos directo de Google Maps (más robusto).

### Pasos

1. **Obtener Google Maps API Key**:
   - Google Cloud Console → Maps API

2. **Instalar Selenium**:
   ```bash
   pip install selenium
   ```

3. **Descargar ChromeDriver**: https://chromedriver.chromium.org/

4. **Implementar scraping**:

```python
from selenium import webdriver
from selenium.webdriver.common.by import By

def buscar_en_google(self):
    driver = webdriver.Chrome("./chromedriver")
    
    search_url = f"https://www.google.com/maps/search/{self.nicho}+en+{self.localizacion}"
    driver.get(search_url)
    
    # Esperar y extraer datos de los resultados
    time.sleep(3)
    
    results = driver.find_elements(By.CLASS_NAME, "Nv2PK")
    
    leads = []
    for result in results:
        # Extraer nombre, teléfono, sitio web...
        pass
    
    driver.quit()
    return leads
```

---

## 📌 Opción 4: Python-Google-Places (Alternativa)

### Instalar:
```bash
pip install python-google-places
```

### Usar:
```python
from googleplaces import GooglePlaces

def buscar_en_google(self):
    google_places = GooglePlaces(api_key=os.getenv("GOOGLE_PLACES_API_KEY"))
    
    query_result = google_places.nearby_search(
        lat=self.get_lat_lon(self.localizacion)[0],
        lng=self.get_lat_lon(self.localizacion)[1],
        radius=15000,
        keyword=self.nicho
    )
    
    leads = []
    for place in query_result.places:
        leads.append({
            "nombre": place.name,
            "telefono": place.local_phone_number,
            "email": place.website,  # URLs en lugar de email
            "direccion": place.formatted_address,
            "tiene_web": bool(place.website),
            "url": place.website
        })
    
    return leads
```

---

## 🔑 Archivos de Configuración

### Crear `.env` en la raíz del proyecto:

```bash
# SerpAPI
SERPAPI_KEY=tu_key_aqui

# Google Search
GOOGLE_SEARCH_API_KEY=tu_key_aqui
GOOGLE_SEARCH_ENGINE_ID=tu_id_aqui

# Google Places
GOOGLE_PLACES_API_KEY=tu_key_aqui

# Selenium (si usas)
CHROMEDRIVER_PATH=./chromedriver.exe
```

### Instalar python-dotenv:
```bash
pip install python-dotenv
```

### En `cazador_leads.py`, al inicio:
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 🚀 Pasos Finales

1. **Elegir API** (recomendado: SerpAPI)
2. **Crear cuenta y obtener key**
3. **Instalar dependencias**: `pip install -r requirements.txt`
4. **Configurar .env**
5. **Modificar sección de búsqueda en `cazador_leads.py`**
6. **Ejecutar**: `python cazador_leads.py`

---

## ⚙️ Archivo `requirements.txt`

```
requests==2.28.2
beautifulsoup4==4.11.1
google-search-results==2.4.2
python-dotenv==0.21.0
google-api-python-client==2.86.0
selenium==4.10.0
```

Instalar todo:
```bash
pip install -r requirements.txt
```

---

## 🔍 Validación de Emails

Una vez tengas los leads, **siempre validar emails** antes de enviar:

```python
import re

def validar_email(email):
    """Validación básica de formato"""
    patron = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(patron, email) is not None

# O usar API externa:
# https://www.sendgrid.com/en-us/solutions/email-verification
```

---

## ⚠️ Limitaciones y Notas

- **SerpAPI**: 100 búsquedas gratis/mes, luego $0.02-0.10 cada una
- **Google Search**: 100/día gratis, pero requiere setup más complejo
- **Selenium**: Más lento, pero más confiable para scraping
- **Telephones/Emails**: Pueden no estar siempre disponibles en Google Maps

---

## 🎯 Recomendación Final

**Usa SerpAPI** para empezar:
1. Es gratis durante 100 búsquedas
2. Requiere menos código
3. Datos más limpios
4. Fácil de escalar
