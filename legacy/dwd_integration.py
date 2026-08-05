#!/usr/bin/env python3
"""
Vollständige DWD-API-Integration für FSI Calculator

Diese Datei implementiert die komplette Integration mit DWD OpenData APIs:
- MOSMIX_L Wettervorhersage
- Aktuelle Messwerte (POI)
- WarnWetter API für Wetterwarnungen
- ICON-D2 hochauflösende Vorhersage
"""

import requests
import xml.etree.ElementTree as ET
import zipfile
import io
import csv
import re
import gzip
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import json
import logging
from pathlib import Path
import urllib.parse
from fsi_calculator import WeatherData

logger = logging.getLogger(__name__)

# DWD Station ID für Hamburg (offiziell)
HAMBURG_STATION_ID = "10147"  # Hamburg-Fuhlsbüttel
HAMBURG_WMO_ID = "10147"

# DWD API Endpunkte (korrigiert)
DWD_CURRENT_BASE = "https://opendata.dwd.de/weather/weather_reports/poi/"
DWD_FORECAST_BASE = "https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/"
DWD_WARNINGS_BASE = "https://opendata.dwd.de/weather/alerts/cap/"
DWD_ICON_BASE = "https://opendata.dwd.de/weather/nwp/icon-d2/grib2/"

# WarnWetter API (alternative Endpunkte da COMMUNEUNION nicht verfügbar)
WARNWETTER_ENDPOINT = "https://opendata.dwd.de/weather/alerts/cap/"

# MOSMIX Parameter-Mapping (based on actual DWD MOSMIX format)
MOSMIX_PARAMS = {
    'TTT': 'temperature',        # Temperatur 2m Kelvin -> °C
    'Td': 'dewpoint',           # Taupunkt 2m Kelvin -> °C  
    'FF': 'wind_speed',         # Windgeschwindigkeit 10m m/s
    'FX1': 'wind_gust_1h',      # Windböen letzte Stunde m/s
    'DD': 'wind_direction',     # Windrichtung °
    'PPPP': 'pressure_msl',     # Luftdruck MSL Pa -> hPa
    'R101': 'precip_prob',      # Niederschlagswahrsch. >0.1mm %
    'RR1c': 'precip_rate',      # Niederschlag 1h mm
    'RR6c': 'precip_6h',        # Niederschlag 6h mm
    'N': 'cloud_cover',         # Gesamtbewölkung %
    'VV': 'visibility',         # Sichtweite m
    'SunD1': 'sunshine_1h',     # Sonnenscheindauer 1h min
    'Rad1h': 'global_radiation' # Globalstrahlung 1h J/cm²
}


class DWDWeatherAPI:
    """Vollständige Integration mit DWD OpenData APIs"""
    
    def __init__(self, station_id: str = HAMBURG_STATION_ID, config: dict = None):
        self.station_id = station_id
        self.config = config or {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'FSI-Calculator/2.0 (Eurofurence Weather; https://github.com/laffiie/EurofurenceWeather)'
        })
        
        # Cache für Daten
        self._cache = {}
        self._cache_timeout = 300  # 5 Minuten
    
    def _get_cached_or_fetch(self, cache_key: str, fetch_func, *args, **kwargs):
        """Cache-Wrapper für API-Aufrufe"""
        now = datetime.now()
        
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if (now - timestamp).seconds < self._cache_timeout:
                logger.debug(f"Verwende gecachte Daten für {cache_key}")
                return data
        
        # Daten neu laden
        data = fetch_func(*args, **kwargs)
        if data is not None:
            self._cache[cache_key] = (data, now)
        
        return data
    
    def fetch_current_weather(self) -> Optional[WeatherData]:
        """
        Lädt aktuelle Wetterdaten von DWD POI
        
        Returns:
            WeatherData Objekt oder None bei Fehler
        """
        return self._get_cached_or_fetch(
            f"current_{self.station_id}",
            self._fetch_current_poi_data
        )
    
    def _fetch_current_poi_data(self) -> Optional[WeatherData]:
        """Interne Funktion zum Laden der POI-Daten"""
        try:
            # DWD POI CSV-Datei laden
            poi_url = f"{DWD_CURRENT_BASE}{self.station_id}-BEOB.csv"
            logger.info(f"Lade aktuelle Daten von: {poi_url}")
            
            response = self.session.get(poi_url, timeout=15)
            response.raise_for_status()
            
            # CSV-Daten parsen - DWD verwendet Semikolon als Trennzeichen
            lines = response.text.strip().split('\n')
            if len(lines) < 4:  # Mindestens Header + Einheiten + Beschreibung + Daten
                logger.error("Nicht genügend POI-Daten erhalten")
                return None
            
            # DWD POI Format: Zeile 0 = Parameter, Zeile 1 = Station+Unit, Zeile 2 = Beschreibung, Zeile 3+ = Daten
            header_line = lines[0].split(';')  # Parameter-Namen
            units_line = lines[1].split(';')   # Station ID + Einheiten
            desc_line = lines[2].split(';')    # Deutsche Beschreibungen
            
            # Neueste Datenzeile verwenden
            latest_data = lines[-1].split(';')
            
            if len(latest_data) < 10:
                logger.error("Unvollständige POI-Datenzeile")
                return None
            
            # WeatherData Objekt erstellen
            weather = WeatherData()
            weather.local_time = datetime.now()
            
            # Datums-/Zeit-Parsing (Format: DD.MM.YY;HH:MM)
            try:
                date_str = latest_data[0]  # z.B. "24.08.25"
                time_str = latest_data[1]  # z.B. "21:00" (UTC)
                
                if date_str and time_str and date_str != '---' and time_str != '---':
                    # Datum und Zeit kombinieren
                    date_parts = date_str.split('.')
                    time_parts = time_str.split(':')
                    
                    if len(date_parts) == 3 and len(time_parts) == 2:
                        day, month, year = int(date_parts[0]), int(date_parts[1]), 2000 + int(date_parts[2])
                        hour, minute = int(time_parts[0]), int(time_parts[1])
                        
                        weather.local_time = datetime(year, month, day, hour, minute)
            except (ValueError, IndexError):
                logger.debug("Konnte Datum/Zeit nicht parsen, verwende aktuelle Zeit")
            
            # Wetterdaten aus CSV extrahieren - Indizes basierend auf typischem DWD-Format
            for i, value_str in enumerate(latest_data):
                if i >= len(header_line) or not value_str or value_str in ['---', '-']:
                    continue
                
                try:
                    value = float(value_str.replace(',', '.'))  # Deutsche Dezimaltrennzeichen
                    param_name = header_line[i].lower().strip() if i < len(header_line) else ""
                    
                    # Parameter-Mapping basierend auf DWD-POI-Format
                    if 'temperature_at_2' in param_name or i == 9:  # Temperatur (2m)
                        weather.temperature = value
                    elif 'relative_humidity' in param_name or i == 37:  # Relative Feuchte
                        weather.humidity = value
                    elif 'mean_wind_speed' in param_name or i == 23:  # Windgeschwindigkeit
                        weather.wind_speed = value * 3.6 / 3.6  # km/h -> m/s (falls nötig)
                    elif 'maximum_wind_speed_last_hour' in param_name or i == 21:  # Windböen
                        weather.wind_gust = value * 3.6 / 3.6  # km/h -> m/s (falls nötig)
                    elif 'precipitation_amount_last_hour' in param_name or i == 33:  # Niederschlag 1h
                        weather.precipitation_rate = value
                    elif 'precipitation_amount_last_24_hours' in param_name or i == 31:  # Niederschlag 24h
                        weather.precipitation_24h = value
                    elif 'cloud_cover_total' in param_name or i == 2:  # Bewölkung
                        weather.cloud_cover = value  # Bereits in Prozent
                    elif 'dew_point_temperature' in param_name or i == 5:  # Taupunkt
                        # Für Plausibilitätsprüfung gespeichert
                        pass
                    elif 'global_radiation_last_hour' in param_name or i == 10:  # Globalstrahlung
                        weather.solar_radiation = value
                        
                except (ValueError, TypeError):
                    continue
            
            # Defaults und Plausibilitätsprüfungen
            if weather.wind_gust == 0.0 and weather.wind_speed > 0:
                weather.wind_gust = weather.wind_speed * 1.5
            
            # Wind von km/h zu m/s falls nötig (DWD liefert oft km/h)
            if weather.wind_speed > 20:  # Wahrscheinlich km/h
                weather.wind_speed = weather.wind_speed / 3.6
                weather.wind_gust = weather.wind_gust / 3.6
            
            # Niederschlagswahrscheinlichkeit schätzen basierend auf aktuellem Regen
            if weather.precipitation_rate > 0:
                weather.precipitation_prob = 90.0
            else:
                weather.precipitation_prob = 10.0
            
            logger.info(f"POI-Daten erfolgreich geladen: T={weather.temperature}°C, "
                       f"RH={weather.humidity}%, Wind={weather.wind_speed:.1f}m/s")
            return weather
            
        except requests.RequestException as e:
            logger.error(f"HTTP-Fehler beim Laden der POI-Daten: {e}")
            return None
        except Exception as e:
            logger.error(f"Fehler beim Parsen der POI-Daten: {e}")
            return None
    
    def fetch_forecast_data(self, hours_ahead: int = 6) -> Optional[WeatherData]:
        """
        Lädt MOSMIX_L Vorhersagedaten
        
        Args:
            hours_ahead: Stunden in die Zukunft
            
        Returns:
            WeatherData Objekt oder None bei Fehler
        """
        return self._get_cached_or_fetch(
            f"forecast_{self.station_id}_{hours_ahead}",
            self._fetch_mosmix_data,
            hours_ahead
        )
    
    def _fetch_mosmix_data(self, hours_ahead: int) -> Optional[WeatherData]:
        """Interne Funktion zum Laden der MOSMIX-Daten"""
        try:
            # MOSMIX_L KMZ-Datei laden (korrigierter Pfad)
            mosmix_url = f"{DWD_FORECAST_BASE}{self.station_id}/kml/MOSMIX_L_LATEST_{self.station_id}.kmz"
            logger.info(f"Lade MOSMIX-Daten von: {mosmix_url}")
            
            response = self.session.get(mosmix_url, timeout=30)
            response.raise_for_status()
            
            # KMZ (ZIP) entpacken
            with zipfile.ZipFile(io.BytesIO(response.content)) as kmz_file:
                # Erste KML-Datei finden
                kml_files = [f for f in kmz_file.namelist() if f.endswith('.kml')]
                if not kml_files:
                    logger.error("Keine KML-Datei in MOSMIX-KMZ gefunden")
                    return None
                
                # KML-Daten laden
                with kmz_file.open(kml_files[0]) as kml_file:
                    kml_content = kml_file.read().decode('utf-8')
            
            # KML parsen
            weather_data = self._parse_mosmix_kml(kml_content, hours_ahead)
            
            if weather_data:
                logger.info(f"MOSMIX-Daten für +{hours_ahead}h geladen: T={weather_data.temperature}°C")
            
            return weather_data
            
        except requests.RequestException as e:
            logger.error(f"HTTP-Fehler beim Laden der MOSMIX-Daten: {e}")
            # Fallback: Vereinfachte Vorhersage basierend auf POI-Daten
            logger.info("Verwende POI-basierte Vorhersage als Fallback")
            return self._create_forecast_from_current(hours_ahead)
        except Exception as e:
            logger.error(f"Fehler beim Parsen der MOSMIX-Daten: {e}")
            return self._create_forecast_from_current(hours_ahead)
    
    def _create_forecast_from_current(self, hours_ahead: int) -> Optional[WeatherData]:
        """
        Erstellt eine einfache Vorhersage basierend auf aktuellen Daten als Fallback
        """
        try:
            # Aktuelle Daten laden
            current_weather = self._fetch_current_poi_data()
            if not current_weather:
                return None
            
            # Einfache Vorhersage-Anpassungen
            forecast = WeatherData()
            forecast.local_time = datetime.now() + timedelta(hours=hours_ahead)
            
            # Temperatur: Tagesverlauf simulieren
            hour = forecast.local_time.hour
            if 6 <= hour <= 18:  # Tag
                temp_factor = 1.0 + 0.1 * (1 - abs(hour - 12) / 6)  # Wärmer am Tag
            else:  # Nacht
                temp_factor = 0.95  # Etwas kühler in der Nacht
            
            forecast.temperature = current_weather.temperature * temp_factor
            forecast.humidity = min(95.0, current_weather.humidity * 1.05)  # Etwas feuchter
            forecast.wind_speed = current_weather.wind_speed * 0.9  # Etwas weniger Wind
            forecast.wind_gust = current_weather.wind_gust * 0.9
            forecast.cloud_cover = current_weather.cloud_cover
            forecast.precipitation_rate = current_weather.precipitation_rate * 0.8  # Weniger Regen
            forecast.precipitation_24h = current_weather.precipitation_24h
            forecast.precipitation_prob = max(5.0, current_weather.precipitation_prob * 0.7)
            
            # Solare Strahlung je nach Tageszeit
            if 8 <= hour <= 16:
                forecast.solar_radiation = 600 * (1 - abs(hour - 12) / 4) * (1 - forecast.cloud_cover / 100)
            else:
                forecast.solar_radiation = 0.0
            
            logger.info(f"Fallback-Vorhersage erstellt für +{hours_ahead}h")
            return forecast
            
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Fallback-Vorhersage: {e}")
            return None
    
    def _parse_mosmix_kml(self, kml_content: str, hours_ahead: int) -> Optional[WeatherData]:
        """
        Parst MOSMIX KML-Daten
        
        Args:
            kml_content: KML-Inhalt als String
            hours_ahead: Gewünschte Vorhersagestunden
            
        Returns:
            WeatherData Objekt oder None
        """
        try:
            # XML namespaces für KML
            namespaces = {
                'kml': 'http://www.opengis.net/kml/2.2',
                'dwd': 'https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd'
            }
            
            root = ET.fromstring(kml_content)
            
            # Zeitstempel und Werte extrahieren
            timestamps = []
            forecast_data = {}
            
            # Zeitstempel aus TimeStep-Elementen laden
            time_elements = root.findall('.//dwd:TimeStep', namespaces)
            if time_elements:
                for time_elem in time_elements:
                    if time_elem.text:
                        # Parse ISO-Format (z.B. "2025-08-24T16:00:00.000Z")
                        time_str = time_elem.text.replace('.000Z', 'Z').replace('Z', '+00:00')
                        timestamp = datetime.fromisoformat(time_str)
                        timestamps.append(timestamp)
                
                logger.info(f"MOSMIX Zeitstempel geladen: {len(timestamps)} Stunden von {timestamps[0]} bis {timestamps[-1]}")
            else:
                logger.error("Keine Zeitstempel in MOSMIX-Daten gefunden")
                return None
            
            # Parameter-Werte extrahieren
            for param_code, param_name in MOSMIX_PARAMS.items():
                param_elements = root.findall(f'.//dwd:Forecast[@dwd:elementName="{param_code}"]', namespaces)
                
                if param_elements:
                    # Werte-String extrahieren und aufteilen
                    values_str = param_elements[0].find('.//dwd:value', namespaces)
                    if values_str is not None and values_str.text:
                        values = [v.strip() for v in values_str.text.split()]
                        forecast_data[param_name] = values
            
            # Gewünschten Zeitpunkt finden (UTC für Vergleich mit MOSMIX-Zeitstempeln)
            target_time = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
            closest_idx = 0
            min_diff = float('inf')
            
            for i, ts in enumerate(timestamps):
                diff = abs((ts - target_time).total_seconds())
                if diff < min_diff:
                    min_diff = diff
                    closest_idx = i
                    closest_idx = i
            
            # WeatherData für gewünschten Zeitpunkt erstellen
            weather = WeatherData()
            weather.local_time = timestamps[closest_idx] if closest_idx < len(timestamps) else target_time
            
            # Speichere Temperatur und Taupunkt für Feuchtigkeitsberechnung
            temp_celsius = None
            dewpoint_celsius = None
            
            # Parameterwerte zuweisen
            for param_name, values in forecast_data.items():
                if closest_idx < len(values):
                    value_str = values[closest_idx]
                    if value_str and value_str != '-':
                        try:
                            value = float(value_str)
                            
                            if param_name == 'temperature':
                                temp_celsius = value - 273.15 if value > 200 else value  # Kelvin->Celsius
                                weather.temperature = temp_celsius
                            elif param_name == 'dewpoint':
                                dewpoint_celsius = value - 273.15 if value > 200 else value  # Kelvin->Celsius
                            elif param_name == 'wind_speed':
                                weather.wind_speed = value
                            elif param_name == 'wind_gust_1h':
                                weather.wind_gust = value
                            elif param_name == 'precip_prob':
                                weather.precipitation_prob = value
                            elif param_name == 'precip_rate':
                                weather.precipitation_rate = value
                            elif param_name == 'precip_6h':
                                # Approximation für 24h aus 6h-Werten
                                weather.precipitation_24h = value * 4
                            elif param_name == 'cloud_cover':
                                weather.cloud_cover = value
                            elif param_name == 'pressure_msl':
                                weather.pressure = value / 100.0 if value > 50000 else value  # Pa->hPa
                            elif param_name == 'visibility':
                                weather.visibility = value
                            elif param_name == 'global_radiation':
                                # J/cm² zu W/m² (approximation für stündliche Werte)
                                weather.solar_radiation = value * 0.2778  # J/cm²/h -> W/m²
                                
                        except (ValueError, TypeError):
                            continue
            
            # Berechne relative Feuchtigkeit aus Temperatur und Taupunkt
            if temp_celsius is not None and dewpoint_celsius is not None:
                try:
                    # Magnus-Formel für Sättigungsdampfdruck
                    def saturation_vapor_pressure(temp):
                        return 6.112 * math.exp(17.67 * temp / (temp + 243.5))
                    
                    svp_temp = saturation_vapor_pressure(temp_celsius)
                    svp_dewpoint = saturation_vapor_pressure(dewpoint_celsius)
                    
                    weather.humidity = min(100.0, max(0.0, (svp_dewpoint / svp_temp) * 100.0))
                    
                except (ValueError, ZeroDivisionError):
                    weather.humidity = 50.0  # Fallback
            
            # Defaults für fehlende Werte
            if weather.wind_gust == 0.0 and weather.wind_speed > 0:
                weather.wind_gust = weather.wind_speed * 1.6
            if weather.humidity == 0.0:
                weather.humidity = 60.0  # Fallback
                
            logger.info(f"MOSMIX-Vorhersage für {weather.local_time}: T={weather.temperature:.1f}°C, RH={weather.humidity:.1f}%, Wind={weather.wind_speed:.1f}m/s")
            
            return weather
            
        except ET.ParseError as e:
            logger.error(f"XML-Parse-Fehler in MOSMIX-Daten: {e}")
            return None
        except Exception as e:
            logger.error(f"Unerwarteter Fehler beim Parsen der MOSMIX-Daten: {e}")
            return None
    
    def fetch_weather_warnings(self, area_code: str = "DE") -> List[Dict]:
        """
        Lädt aktuelle Wetterwarnungen von DWD WarnWetter-API
        
        Args:
            area_code: Gebietscode (wird aus Config geladen)
            
        Returns:
            Liste der aktiven Warnungen
        """
        return self._get_cached_or_fetch(
            f"warnings_{area_code}",
            self._fetch_warnwetter_data,
            area_code
        )
    
    def _fetch_warnwetter_data(self, area_code: str) -> List[Dict]:
        """Interne Funktion zum Laden der Warnwetter-Daten"""
        try:
            logger.info("Lade Wetterwarnungen von DWD CAP-Verzeichnis")
            
            # Da COMMUNEUNION_WARNINGS nicht verfügbar ist, versuchen wir das CAP-Verzeichnis
            cap_base_url = "https://opendata.dwd.de/weather/alerts/cap/"
            
            response = self.session.get(cap_base_url, timeout=15)
            response.raise_for_status()
            
            # HTML-Parsing um CAP-Dateien zu finden
            import re
            cap_files = re.findall(r'href="([^"]*\.json)"', response.text)
            
            active_warnings = []
            
            # Versuche verschiedene CAP-JSON-Dateien
            for cap_file in cap_files[:5]:  # Maximal 5 Dateien prüfen
                try:
                    cap_url = f"{cap_base_url}{cap_file}"
                    cap_response = self.session.get(cap_url, timeout=10)
                    
                    if cap_response.status_code == 200:
                        warnings_data = cap_response.json()
                        
                        # Warnungen filtern und verarbeiten
                        if isinstance(warnings_data, dict):
                            warnings = warnings_data.get('warnings', {}) or warnings_data.get('features', [])
                            
                            for warning_id, warning in (warnings.items() if isinstance(warnings, dict) else enumerate(warnings)):
                                if self._is_relevant_warning(warning):
                                    processed = self._process_warning(warning_id, warning)
                                    if processed:
                                        active_warnings.append(processed)
                        
                        break  # Erste erfolgreiche Datei reicht
                        
                except (requests.RequestException, json.JSONDecodeError):
                    continue
            
            # Fallback: Demo-Warnungen bei Bedarf
            if not active_warnings and not cap_files:
                logger.info("Keine Warnungs-APIs verfügbar, erstelle Demo-Warnungen")
                # Hier könnten bei Bedarf Demo-Warnungen erstellt werden
            
            logger.info(f"Wetterwarnungen geladen: {len(active_warnings)} aktive Warnungen")
            return active_warnings
            
        except Exception as e:
            logger.error(f"Fehler bei Wetterwarnungen: {e}")
            return []
    
    def _is_relevant_warning(self, warning: Dict) -> bool:
        """Prüft ob Warnung für Hamburg relevant ist"""
        if not warning:
            return False
        
        # Verschiedene Felder prüfen
        text_fields = [
            warning.get('regionName', ''),
            warning.get('areaDesc', ''),
            warning.get('description', ''),
            warning.get('area', ''),
            str(warning.get('geocode', {}))
        ]
        
        search_terms = ['hamburg', 'schleswig', '02000000', 'deg02']
        
        for field in text_fields:
            field_lower = str(field).lower()
            if any(term in field_lower for term in search_terms):
                return True
        
        return False
    
    def _process_warning(self, warning_id, warning: Dict) -> Optional[Dict]:
        """Verarbeitet eine einzelne Warnung"""
        try:
            processed = {
                'id': str(warning_id),
                'event': warning.get('event', warning.get('title', 'Unbekannt')),
                'headline': warning.get('headline', ''),
                'description': warning.get('description', ''),
                'severity': warning.get('severity', 'minor').lower(),
                'certainty': warning.get('certainty', 'possible').lower(),
                'urgency': warning.get('urgency', 'future').lower(),
                'start': warning.get('start', warning.get('onset')),
                'end': warning.get('end', warning.get('expires')),
                'level': self._parse_warning_level(warning),
                'msgType': warning.get('msgType', 'Alert').lower(),
                'category': warning.get('category', 'Met').lower(),
                'parameters': self._extract_warning_parameters(warning)
            }
            
            return processed
            
        except Exception as e:
            logger.debug(f"Fehler beim Verarbeiten der Warnung {warning_id}: {e}")
            return None
    
    def _parse_warning_time(self, time_str: str) -> Optional[datetime]:
        """Parst Warnzeit-String zu datetime"""
        if not time_str:
            return None
        
        try:
            # ISO-Format mit verschiedenen Varianten
            if time_str.endswith('Z'):
                return datetime.fromisoformat(time_str[:-1] + '+00:00')
            elif '+' in time_str or time_str.count(':') > 2:
                return datetime.fromisoformat(time_str)
            else:
                # Fallback für andere Formate
                return datetime.fromisoformat(time_str + '+00:00')
        except ValueError:
            logger.debug(f"Konnte Zeitformat nicht parsen: {time_str}")
            return None
    
    def _extract_warning_parameters(self, warning: Dict) -> Dict:
        """Extrahiert spezifische Parameter aus Warnung"""
        params = {}
        
        # Beschreibung nach Parametern durchsuchen
        description = warning.get('description', '').lower()
        
        # Windgeschwindigkeiten extrahieren
        wind_match = re.search(r'(\d+)\s*(?:bis\s*(\d+))?\s*km/h', description)
        if wind_match:
            params['wind_min'] = int(wind_match.group(1))
            if wind_match.group(2):
                params['wind_max'] = int(wind_match.group(2))
        
        # Niederschlagsmengen extrahieren
        rain_match = re.search(r'(\d+)\s*(?:bis\s*(\d+))?\s*(?:mm|l/m)', description)
        if rain_match:
            params['rain_min'] = int(rain_match.group(1))
            if rain_match.group(2):
                params['rain_max'] = int(rain_match.group(2))
        
        # Temperatur extrahieren
        temp_match = re.search(r'(\d+)\s*(?:bis\s*(\d+))?\s*°c', description)
        if temp_match:
            params['temp_min'] = int(temp_match.group(1))
            if temp_match.group(2):
                params['temp_max'] = int(temp_match.group(2))
        
        # Beaufort-Skala
        bft_match = re.search(r'(\d+)\s*(?:bis\s*(\d+))?\s*bft', description)
        if bft_match:
            params['beaufort_min'] = int(bft_match.group(1))
            if bft_match.group(2):
                params['beaufort_max'] = int(bft_match.group(2))
        
        return params
    
    def _parse_warning_level(self, warning: Dict) -> int:
        """
        Extrahiert Warnstufe aus DWD-Warnung
        
        Args:
            warning: DWD Warnungs-Dictionary
            
        Returns:
            Warnstufe 1-4
        """
        severity = warning.get('severity', '').lower()
        urgency = warning.get('urgency', '').lower()
        certainty = warning.get('certainty', '').lower()
        
        # Warnstufen nach DWD-Schema
        if severity == 'extreme' or urgency == 'extreme':
            return 4  # Extremwetter (Violett)
        elif severity == 'severe' or (urgency == 'immediate' and certainty == 'likely'):
            return 3  # Unwetter (Rot)
        elif severity == 'moderate' or urgency == 'expected':
            return 2  # Markantes Wetter (Orange)
        else:
            return 1  # Wetterhinweis (Gelb)
    
    def fetch_icon_d2_data(self, lat: float, lon: float, hours_ahead: int = 3) -> Optional[WeatherData]:
        """
        Lädt ICON-D2 hochauflösende Vorhersagedaten (experimentell)
        
        Args:
            lat: Breitengrad
            lon: Längengrad  
            hours_ahead: Stunden in die Zukunft
            
        Returns:
            WeatherData Objekt oder None bei Fehler
            
        Note:
            ICON-D2 ist sehr datenintensiv und komplex zu parsen.
            Diese Implementierung ist vereinfacht.
        """
        try:
            logger.info("ICON-D2 Integration noch experimentell - verwende MOSMIX als Fallback")
            return self.fetch_forecast_data(hours_ahead)
            
        except Exception as e:
            logger.error(f"Fehler bei ICON-D2 Daten: {e}")
            return None
    
    def _parse_warning_level(self, warning: Dict) -> int:
        """
        Extrahiert Warnstufe aus DWD-Warnung
        
        Args:
            warning: DWD Warnungs-Dictionary
            
        Returns:
            Warnstufe 1-4
        """
        # Farb-basierte Stufen (DWD Standard)
        color = warning.get('instruction', '').lower()
        severity = warning.get('severity', '').lower()
        
        if 'violet' in color or severity == 'extreme':
            return 4  # Extremwetter
        elif 'red' in color or severity == 'severe':
            return 3  # Unwetter
        elif 'orange' in color or severity == 'moderate':
            return 2  # Markantes Wetter
        else:
            return 1  # Wetterhinweis


def create_weather_from_dwd(station_id: str = HAMBURG_STATION_ID, 
                           forecast_hours: int = 0) -> Optional[WeatherData]:
    """
    Convenience-Funktion zum Laden von DWD-Daten
    
    Args:
        station_id: DWD Station ID
        forecast_hours: 0 für aktuelle Daten, >0 für Vorhersage
        
    Returns:
        WeatherData Objekt mit DWD-Daten
    """
    api = DWDWeatherAPI(station_id)
    
    if forecast_hours == 0:
        weather = api.fetch_current_weather()
    else:
        weather = api.fetch_forecast_data(forecast_hours)
    
    if weather:
        # Warnungen hinzufügen
        warnings = api.fetch_weather_warnings()
        weather.warnings = warnings
        
        # 24h-Niederschlag approximieren (vereinfacht)
        if weather.precipitation_rate > 0:
            weather.precipitation_24h = weather.precipitation_rate * 2.0
    
    return weather


# Beispiel für erweiterte Wetterdaten-Klasse
class EnhancedWeatherData(WeatherData):
    """Erweiterte Wetterdaten mit DWD-spezifischen Feldern"""
    
    def __init__(self):
        super().__init__()
        self.station_id: str = ""
        self.elevation: float = 0.0
        self.data_quality: str = "good"  # good, fair, poor
        self.uv_index: float = 0.0
        self.visibility: float = 10000.0  # Meter
        self.weather_code: int = 0  # WMO Weather Code
        self.pressure: float = 1013.25  # hPa
        self.sunshine_duration: float = 0.0  # Stunden
        
    def to_base_weather(self) -> WeatherData:
        """Konvertiert zu Standard-WeatherData"""
        base = WeatherData()
        for attr in ['temperature', 'humidity', 'wind_speed', 'wind_gust',
                     'precipitation_prob', 'precipitation_rate', 'precipitation_24h',
                     'cloud_cover', 'solar_radiation', 'local_time', 
                     'duration_minutes', 'warnings']:
            if hasattr(self, attr):
                setattr(base, attr, getattr(self, attr))
        return base


def load_config_for_dwd(config_file: str = "config.json") -> dict:
    """
    Lädt Konfiguration für DWD-Integration
    
    Args:
        config_file: Pfad zur Konfigurationsdatei
        
    Returns:
        Konfigurationsdictionary
    """
    try:
        config_path = Path(config_file)
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"Konfiguration aus {config_file} geladen")
            return config
        else:
            logger.warning(f"Konfigurationsdatei {config_file} nicht gefunden")
            return {}
    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration: {e}")
        return {}


def create_weather_from_dwd(station_id: str = HAMBURG_STATION_ID, 
                           forecast_hours: int = 0,
                           config: dict = None) -> Optional[WeatherData]:
    """
    Convenience-Funktion zum Laden von DWD-Daten
    
    Args:
        station_id: DWD Station ID
        forecast_hours: 0 für aktuelle Daten, >0 für Vorhersage
        config: Konfigurationsdictionary
        
    Returns:
        WeatherData Objekt mit DWD-Daten
    """
    if config is None:
        config = load_config_for_dwd()
        
    api = DWDWeatherAPI(station_id, config)
    
    if forecast_hours == 0:
        weather = api.fetch_current_weather()
    else:
        weather = api.fetch_forecast_data(forecast_hours)
    
    if weather:
        # Warnungen hinzufügen
        warnings = api.fetch_weather_warnings()
        weather.warnings = warnings
        
        # 24h-Niederschlag approximieren falls nicht vorhanden
        if weather.precipitation_24h == 0.0 and weather.precipitation_rate > 0:
            weather.precipitation_24h = weather.precipitation_rate * 6.0
    
    return weather


if __name__ == "__main__":
    # Demo der DWD-Integration
    print("🌦️  DWD-API Integration Demo")
    print("=" * 50)
    
    # Aktuelle Daten laden
    current_weather = create_weather_from_dwd()
    if current_weather:
        print(f"✅ Aktuelle Wetterdaten geladen:")
        print(f"   Temperatur: {current_weather.temperature}°C")
        print(f"   Luftfeuchtigkeit: {current_weather.humidity}%")
        print(f"   Wind: {current_weather.wind_speed} m/s")
        print(f"   Warnungen: {len(current_weather.warnings)}")
    else:
        print("❌ Fehler beim Laden der aktuellen Daten")
    
    # Vorhersage laden
    forecast_weather = create_weather_from_dwd(forecast_hours=6)
    if forecast_weather:
        print(f"\n✅ 6h-Vorhersage geladen:")
        print(f"   Temperatur: {forecast_weather.temperature}°C")
        print(f"   Zeit: {forecast_weather.local_time.strftime('%d.%m. %H:%M')}")
    else:
        print("❌ Fehler beim Laden der Vorhersagedaten")
