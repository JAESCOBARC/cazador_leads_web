@echo off
chcp 65001 >nul
cls

echo ========================================
echo   CAZADOR LEADS WEB - EJECUTOR
echo ========================================
echo.

REM Verificar que Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ERROR: Python no está instalado o no está en PATH
    echo Por favor instala Python desde https://www.python.org/
    pause
    exit /b 1
)

echo ✓ Python detectado
echo.

REM Verificar que existe el archivo principal
if not exist "cazador_leads.py" (
    echo ❌ ERROR: No se encontró cazador_leads.py
    pause
    exit /b 1
)

echo ✓ Archivo principal encontrado
echo.

REM Instalar dependencias si existe requirements.txt
if exist "requirements.txt" (
    echo Instalando dependencias...
    python -m pip install -q -r requirements.txt
    if errorlevel 1 (
        echo ❌ ERROR al instalar dependencias
        pause
        exit /b 1
    )
    echo ✓ Dependencias instaladas
    echo.
)

REM Ejecutar el programa principal
echo ========================================
echo Iniciando búsqueda de prospects...
echo ========================================
echo.

python cazador_leads.py

echo.
echo ========================================
echo Ejecución completada
echo ========================================
pause
