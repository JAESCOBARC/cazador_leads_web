#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueba: geocodificar ciudad+país -> lat/lng -> usar como `ll` en SerpAPI google_maps"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
serpapi_key = os.getenv("SERPAPI_KEY")


def geocodificar(ciudad, pais):
    """Usa Nominatim (OpenStreetMap) para convertir ciudad+país en lat/lng reales"""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"{ciudad}, {pais}", "format": "json", "limit": 1}
    headers = {"User-Agent": "CazadorLeadsWeb/1.0 (test script)"}

    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    resultados = r.json()

    if not resultados:
        return None

    return {
        "lat": float(resultados[0]["lat"]),
        "lon": float(resultados[0]["lon"]),
        "display_name": resultados[0]["display_name"]
    }


casos = [
    ("pizzeria", "Dosquebradas", "Colombia"),
    ("pizzeria", "Madrid", "Colombia"),   # Ambiguo con España
    ("pizzeria", "Madrid", "España"),      # El otro Madrid
]

for nicho, ciudad, pais in casos:
    print("=" * 70)
    print(f"NICHO: {nicho} | CIUDAD: {ciudad} | PAÍS: {pais}")
    print("=" * 70)

    geo = geocodificar(ciudad, pais)
    if not geo:
        print("  ❌ No se pudo geocodificar")
        continue

    print(f"  📍 Geocodificado a: {geo['display_name']}")
    print(f"  📍 Coordenadas: {geo['lat']}, {geo['lon']}")

    ll = f"@{geo['lat']},{geo['lon']},14z"
    params = {
        "engine": "google_maps",
        "q": nicho,
        "ll": ll,
        "api_key": serpapi_key
    }

    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        status = response.status_code
        data = response.json()

        if status != 200 or "error" in data:
            print(f"  ❌ Status {status} | Error: {data.get('error', 'N/A')}")
        else:
            local_results = data.get("local_results", [])
            print(f"  ✅ Status {status} | {len(local_results)} resultados REALES")
            for place in local_results[:5]:
                website = place.get("website", "")
                estado = "CON WEB" if website else "SIN WEB"
                print(f"     - {place.get('title', 'N/A')} | {place.get('address', 'N/A')} | {estado}")
    except Exception as e:
        print(f"  ❌ Excepción: {e}")

    print()
