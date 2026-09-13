#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cazador Leads Web — API Flask
Expone la funcionalidad de búsqueda como servicio web
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pathlib import Path
from cazador_leads import CazadorLeads

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

BASE_DIR = Path(__file__).parent


@app.route('/')
def index():
    """Sirve la página principal"""
    return render_template('index.html')


@app.route('/api/buscar', methods=['POST'])
def buscar():
    """API endpoint para buscar prospects"""
    try:
        data = request.json
        nicho = data.get('nicho', '').strip()
        ciudad = data.get('ciudad', '').strip()
        pais = data.get('pais', '').strip()

        print(f"[DEBUG] Búsqueda recibida: nicho='{nicho}', ciudad='{ciudad}', pais='{pais}'")

        if not nicho or not ciudad or not pais:
            return jsonify({'error': 'Nicho, ciudad y país son requeridos'}), 400

        # Guardar inputs en archivos
        nicho_file = BASE_DIR / 'nicho.txt'
        ciudad_file = BASE_DIR / 'ciudad.txt'
        pais_file = BASE_DIR / 'pais.txt'

        with open(nicho_file, 'w', encoding='utf-8') as f:
            f.write(nicho)
        with open(ciudad_file, 'w', encoding='utf-8') as f:
            f.write(ciudad)
        with open(pais_file, 'w', encoding='utf-8') as f:
            f.write(pais)

        print(f"[DEBUG] Archivos guardados: {nicho_file}, {ciudad_file}, {pais_file}")

        # Ejecutar búsqueda con datos pasados directamente
        cazador = CazadorLeads(base_dir=BASE_DIR)
        cazador.nicho = nicho
        cazador.ciudad = ciudad
        cazador.pais = pais
        cazador.localizacion = f"{ciudad}, {pais}"

        print(f"[DEBUG] Iniciando búsqueda con: {nicho} en {ciudad}, {pais}")

        resultados = cazador.buscar_en_google()
        leads = cazador.filtrar_sin_web(resultados)

        print(f"[DEBUG] Leads encontrados: {len(leads)}")

        if not leads:
            error_msg = cazador.error_busqueda or 'No se encontraron negocios sin web para esta búsqueda'
            return jsonify({'error': error_msg}), 404

        # Generar mensajes personalizados (WhatsApp/email/teléfono según lo real disponible)
        emails_generados = []
        for i, lead in enumerate(leads, 1):
            email_data = cazador.generar_mensaje_personalizado(lead, i)
            emails_generados.append(email_data)

        # Guardar output
        cazador.leads = leads
        cazador.guardar_output(emails_generados)

        print(f"[DEBUG] Emails generados: {len(emails_generados)}")

        # Retornar resultados formateados (el total refleja lo REAL encontrado, nunca se completa)
        resultado_api = {
            'nicho': nicho,
            'ciudad': ciudad,
            'pais': pais,
            'total': len(emails_generados),
            'advertencia': (
                f'Solo se encontraron {len(emails_generados)} negocios reales sin web '
                f'(se buscaban hasta {cazador.max_results}). Esto es lo real disponible en Google Maps para esta búsqueda.'
                if len(emails_generados) < cazador.max_results else None
            ),
            'leads': [
                {
                    'numero': e['numero'],
                    'nombre': e['nombre'],
                    'telefono': e['telefono'],
                    'whatsapp': e['whatsapp'],
                    'whatsapp_confirmado': e['whatsapp_confirmado'],
                    'redes_sociales': e['redes_sociales'],
                    'email': e['email'],
                    'canal_recomendado': e['canal_recomendado'],
                    'direccion': e['direccion'],
                    'asunto': e['asunto'],
                    'cuerpo': e['cuerpo']
                }
                for e in emails_generados
            ]
        }

        return jsonify(resultado_api), 200

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/resultados', methods=['GET'])
def obtener_resultados():
    """Obtiene los últimos resultados guardados"""
    try:
        output_file = BASE_DIR / 'prospects_encontrados.md'
        if not output_file.exists():
            return jsonify({'error': 'No hay resultados guardados'}), 404

        with open(output_file, 'r', encoding='utf-8') as f:
            contenido = f.read()

        return jsonify({'contenido': contenido}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
