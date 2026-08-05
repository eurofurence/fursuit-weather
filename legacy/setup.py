#!/usr/bin/env python3
"""
Setup-Skript für den Fursuitability Index Calculator
Installiert Abhängigkeiten und erstellt Konfigurationsdateien
"""

import os
import subprocess
import sys
import json
from pathlib import Path

def check_python_version():
    """Prüft Python-Version"""
    if sys.version_info < (3, 7):
        print("❌ Python 3.7 oder höher erforderlich!")
        print(f"   Aktuelle Version: {sys.version}")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} erkannt")

def install_dependencies():
    """Installiert erforderliche Pakete"""
    print("📦 Installiere Abhängigkeiten...")
    
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("✅ Abhängigkeiten erfolgreich installiert")
        return True
    except subprocess.CalledProcessError:
        print("⚠️  Fehler beim Installieren der Abhängigkeiten")
        print("   Versuche manuelle Installation:")
        print("   pip install requests python-dateutil")
        return False

def create_config_if_missing():
    """Erstellt config.json falls sie nicht existiert"""
    config_path = Path("config.json")
    
    if config_path.exists():
        print("✅ Konfigurationsdatei bereits vorhanden")
        return
    
    print("📝 Erstelle Konfigurationsdatei...")
    
    default_config = {
        "location": {
            "name": "Hamburg",
            "lat": 53.561337,
            "lon": 9.986310
        },
        "dwd": {
            "station_id": "10147",
            "timeout": 10
        },
        "fsi_thresholds": {
            "excellent": 8.0,
            "good": 6.0,
            "fair": 4.0,
            "poor": 2.0
        },
        "weights": {
            "thermal_humidity": 0.4,
            "precipitation": 0.35,
            "wind": 0.15,
            "stickiness": 0.1
        }
    }
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        print("✅ Standard-Konfiguration erstellt")
    except Exception as e:
        print(f"⚠️  Fehler beim Erstellen der Konfiguration: {e}")

def create_shell_scripts():
    """Erstellt Shell-Skripte für einfache Nutzung"""
    
    # Unix Shell Script
    bash_script = """#!/bin/bash
# Fursuitability Index - Quick Access Script
cd "$(dirname "$0")"
python3 fsi_cli.py --dwd "$@"
"""
    
    # Windows Batch Script  
    batch_script = """@echo off
REM Fursuitability Index - Quick Access Script
cd /d "%~dp0"
python fsi_cli.py --dwd %*
"""
    
    try:
        # Unix Script
        with open("fsi.sh", 'w') as f:
            f.write(bash_script)
        os.chmod("fsi.sh", 0o755)
        
        # Windows Script
        with open("fsi.bat", 'w') as f:
            f.write(batch_script)
            
        print("✅ Shell-Skripte erstellt (fsi.sh, fsi.bat)")
    except Exception as e:
        print(f"⚠️  Fehler beim Erstellen der Shell-Skripte: {e}")

def test_installation():
    """Testet die Installation"""
    print("🧪 Teste Installation...")
    
    try:
        # Test import
        from fsi_calculator import compute_fsi, WeatherData
        from dwd_integration import create_weather_from_dwd
        print("✅ Python-Module können importiert werden")
        
        # Test demo calculation
        weather = WeatherData()
        weather.temperature = 20.0
        weather.humidity = 60.0
        weather.wind_speed = 2.0
        
        result = compute_fsi(weather)
        if result and 'fsi' in result:
            print(f"✅ FSI-Berechnung funktioniert (Test-FSI: {result['fsi']}/10)")
        else:
            print("⚠️  FSI-Berechnung fehlgeschlagen")
            
    except ImportError as e:
        print(f"❌ Import-Fehler: {e}")
        print("   Abhängigkeiten möglicherweise nicht korrekt installiert")
    except Exception as e:
        print(f"⚠️  Test-Fehler: {e}")

def main():
    """Hauptfunktion des Setup-Skripts"""
    
    print("🦊 Fursuitability Index Calculator - Setup")
    print("=" * 50)
    
    # 1. Python-Version prüfen
    check_python_version()
    
    # 2. Abhängigkeiten installieren
    deps_ok = install_dependencies()
    
    # 3. Konfiguration erstellen
    create_config_if_missing()
    
    # 4. Shell-Skripte erstellen
    create_shell_scripts()
    
    # 5. Installation testen
    if deps_ok:
        test_installation()
    
    print("\n🎉 Setup abgeschlossen!")
    print("\n🚀 Schnellstart:")
    print("   python fsi_cli.py --dwd")
    print("   ./fsi.sh (Unix/Linux/macOS)")
    print("   fsi.bat (Windows)")
    
    print("\n📚 Hilfe:")
    print("   python fsi_cli.py --help")
    print("   Siehe README.md für ausführliche Dokumentation")

if __name__ == "__main__":
    main()
