#!/usr/bin/env python3
"""
CLI-Interface für den Fursuitability Index Calculator

Kommandozeilen-Tool zur Berechnung des FSI mit verschiedenen Optionen.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fsi_calculator import WeatherData, compute_fsi, fetch_dwd_weather_data
from dwd_integration import create_weather_from_dwd, load_config_for_dwd


def load_config(config_path: str = "config.json") -> dict:
    """Lädt Konfigurationsdatei"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️  Konfigurationsdatei {config_path} nicht gefunden, verwende Standardwerte")
        return {}
    except json.JSONDecodeError as e:
        print(f"❌ Fehler beim Parsen der Konfiguration: {e}")
        return {}


def create_manual_weather(args) -> WeatherData:
    """Erstellt WeatherData-Objekt aus CLI-Argumenten"""
    weather = WeatherData()
    weather.temperature = args.temperature
    weather.humidity = args.humidity
    weather.wind_speed = args.wind_speed
    weather.wind_gust = args.wind_gust or args.wind_speed * 1.5
    weather.precipitation_prob = args.precipitation_prob
    weather.precipitation_rate = args.precipitation_rate
    weather.precipitation_24h = args.precipitation_24h
    weather.cloud_cover = args.cloud_cover
    weather.solar_radiation = args.solar_radiation
    weather.duration_minutes = args.duration
    weather.local_time = datetime.now()
    weather.warnings = []
    
    return weather


def format_fsi_output(result: dict, args, config: dict) -> str:
    """Formatiert FSI-Ausgabe je nach gewünschtem Format"""
    fsi = result['fsi']
    
    if args.format == 'json':
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    
    elif args.format == 'simple':
        return f"{fsi}"
    
    elif args.format == 'brief':
        interpretation = get_fsi_interpretation(fsi, config)
        return f"FSI: {fsi}/10 - {interpretation}"
    
    else:  # detailed
        output = []
        output.append(f"🦊 Fursuitability Index: {fsi}/10")
        output.append(f"📅 {result['timestamp']}")
        output.append(f"📍 {result['location']}")
        output.append(f"📝 {result['reason']}")
        
        if 'subscores' in result:
            output.append("\n📊 Detailbewertung:")
            for category, details in result['subscores'].items():
                cat_name = category.replace('_', ' ').title()
                weight_pct = details['weight'] * 100
                output.append(f"  • {cat_name}: {details['score']:.1f}/10 ({weight_pct:.0f}%)")
        
        if result.get('warnings_applied'):
            output.append(f"\n⚠️  Angewandte Warnungen: {', '.join(result['warnings_applied'])}")
        
        interpretation = get_fsi_interpretation(fsi, config)
        output.append(f"\n🎭 Bewertung: {interpretation}")
        
        return '\n'.join(output)


def get_fsi_interpretation(fsi: float, config: dict) -> str:
    """Gibt Textinterpretation des FSI-Werts zurück"""
    thresholds = config.get('fsi_thresholds', {
        'excellent': 8.0,
        'good': 6.0,
        'fair': 4.0,
        'poor': 2.0
    })
    
    if fsi >= thresholds['excellent']:
        return "🟢 Ausgezeichnet für Fursuiting!"
    elif fsi >= thresholds['good']:
        return "🟡 Gut geeignet mit kleinen Einschränkungen"
    elif fsi >= thresholds['fair']:
        return "🟠 Mäßig geeignet - Vorsicht geboten"
    elif fsi >= thresholds['poor']:
        return "🔴 Schlecht geeignet - kurze Aktivitäten nur"
    else:
        return "⛔ Nicht geeignet - Fursuiting vermeiden!"


def main():
    parser = argparse.ArgumentParser(
        description='Fursuitability Index (FSI) Calculator für Eurofurence',
        epilog="""
Beispiele:
  %(prog)s --dwd                                    # Aktuelle DWD-Daten
  %(prog)s --dwd --forecast 6                      # 6h Vorhersage
  %(prog)s -t 25 -h 70 -w 2.5                     # Manuelle Eingabe
  %(prog)s -t 30 -h 80 --duration 180 --format json # Detaillierte JSON-Ausgabe
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Datenquellen
    data_group = parser.add_mutually_exclusive_group()
    data_group.add_argument(
        '--dwd', action='store_true',
        help='Verwende aktuelle DWD-Daten'
    )
    data_group.add_argument(
        '--demo', action='store_true',
        help='Verwende Demo-Daten'
    )
    
    # DWD-spezifische Optionen
    parser.add_argument(
        '--forecast', type=int, metavar='HOURS',
        help='Verwende Vorhersage für X Stunden in die Zukunft (mit --dwd)'
    )
    parser.add_argument(
        '--station', type=str, default='10147',
        help='DWD Station ID (Standard: 10147 für Hamburg)'
    )
    
    # Manuelle Wetterdaten
    parser.add_argument(
        '-t', '--temperature', type=float, default=22.0,
        help='Temperatur in °C (Standard: 22.0)'
    )
    parser.add_argument(
        '--humidity', type=float, default=60.0,
        help='Relative Feuchte in %% (Standard: 60.0)'
    )
    parser.add_argument(
        '-w', '--wind-speed', type=float, default=2.0,
        help='Windgeschwindigkeit in m/s (Standard: 2.0)'
    )
    parser.add_argument(
        '--wind-gust', type=float,
        help='Windböen in m/s (Standard: 1.5x Windgeschwindigkeit)'
    )
    parser.add_argument(
        '--precipitation-prob', type=float, default=10.0,
        help='Niederschlagswahrscheinlichkeit in %% (Standard: 10.0)'
    )
    parser.add_argument(
        '--precipitation-rate', type=float, default=0.0,
        help='Niederschlagsrate in mm/h (Standard: 0.0)'
    )
    parser.add_argument(
        '--precipitation-24h', type=float, default=0.0,
        help='Niederschlag letzte 24h in mm (Standard: 0.0)'
    )
    parser.add_argument(
        '--cloud-cover', type=float, default=30.0,
        help='Bewölkung in %% (Standard: 30.0)'
    )
    parser.add_argument(
        '--solar-radiation', type=float, default=600.0,
        help='Globalstrahlung in W/m² (Standard: 600.0)'
    )
    parser.add_argument(
        '--duration', type=int, default=60,
        help='Geplante Aktivitätsdauer in Minuten (Standard: 60)'
    )
    
    # Ausgabeoptionen
    parser.add_argument(
        '--format', choices=['detailed', 'brief', 'simple', 'json'],
        default='detailed',
        help='Ausgabeformat (Standard: detailed)'
    )
    parser.add_argument(
        '--config', type=str, default='config.json',
        help='Pfad zur Konfigurationsdatei (Standard: config.json)'
    )
    parser.add_argument(
        '--no-color', action='store_true',
        help='Deaktiviere farbige Ausgabe'
    )
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='Reduzierte Ausgabe (nur bei Fehlern)'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Ausführliche Ausgabe'
    )
    
    args = parser.parse_args()
    
    # Konfiguration laden
    config = load_config_for_dwd(args.config)
    
    # Wetterdaten beschaffen
    weather = None
    
    if args.dwd:
        try:
            forecast_hours = args.forecast or 0
            weather = create_weather_from_dwd(args.station, forecast_hours, config)
            if not weather:
                if not args.quiet:
                    print("❌ DWD-Daten nicht verfügbar", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            if not args.quiet:
                print(f"❌ DWD-Fehler: {e}", file=sys.stderr)
            sys.exit(1)
    
    elif args.demo:
        weather = fetch_dwd_weather_data()
    
    else:
        # Manuelle Eingabe
        weather = create_manual_weather(args)
    
    # Prüfe ob Daten vorhanden
    if not weather:
        print("❌ Keine Wetterdaten verfügbar!", file=sys.stderr)
        sys.exit(1)
    
    # FSI berechnen
    try:
        result = compute_fsi(weather, detailed=(args.format in ['detailed', 'json']))
        
        # Ausgabe formatieren
        output = format_fsi_output(result, args, config)
        print(output)
        
        # Exit-Code basierend auf FSI
        fsi = result['fsi']
        if fsi >= config.get('fsi_thresholds', {}).get('good', 6.0):
            sys.exit(0)  # Gut
        elif fsi >= config.get('fsi_thresholds', {}).get('poor', 2.0):
            sys.exit(1)  # Bedingt
        else:
            sys.exit(2)  # Schlecht
            
    except Exception as e:
        print(f"❌ Fehler bei FSI-Berechnung: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    main()
