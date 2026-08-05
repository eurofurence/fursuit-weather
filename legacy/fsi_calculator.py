#!/usr/bin/env python3
"""
Fursuitability Index (FSI) Calculator for Eurofurence Weather Conditions

Berechnet einen Index von 0-10 für die Eignung von Wetterbedingungen 
zum Fursuiting im Sommer (August/September, Hamburg).

Basiert auf DWD-Opendata (MOSMIX/ICON-D2) und Wetterwarnungen.
"""

import math
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

# Konfiguration für Hamburg
HAMBURG_LAT = 53.561337
HAMBURG_LON = 9.986310
LOCATION_NAME = "Hamburg"

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class WeatherData:
    """Container für Wetterdaten"""
    def __init__(self):
        self.temperature: float = 0.0  # °C
        self.humidity: float = 0.0     # %
        self.wind_speed: float = 0.0   # m/s
        self.wind_gust: float = 0.0    # m/s
        self.precipitation_prob: float = 0.0  # %
        self.precipitation_rate: float = 0.0  # mm/h
        self.precipitation_24h: float = 0.0   # mm
        self.cloud_cover: float = 0.0  # %
        self.solar_radiation: float = 0.0     # W/m²
        self.local_time: datetime = datetime.now()
        self.duration_minutes: int = 60
        self.warnings: List[Dict] = []


def compute_wetbulb_temperature(temp_c: float, humidity_percent: float) -> float:
    """
    Berechnet die Nassbulb-Temperatur nach Stull-Approximation
    
    Args:
        temp_c: Temperatur in °C
        humidity_percent: Relative Feuchte in %
    
    Returns:
        Nassbulb-Temperatur in °C
    """
    T = temp_c
    RH = humidity_percent
    
    # Stull-Approximation für Nassbulb-Temperatur
    T_wb = T * math.atan(0.151977 * (RH + 8.313659) ** 0.5) + \
           math.atan(T + RH) - \
           math.atan(RH - 1.676331) + \
           0.00391838 * (RH ** 1.5) * math.atan(0.023101 * RH) - 4.686035
           
    return round(T_wb, 1)


def compute_dewpoint(temp_c: float, humidity_percent: float) -> float:
    """
    Berechnet den Taupunkt nach Magnus-Formel
    
    Args:
        temp_c: Temperatur in °C
        humidity_percent: Relative Feuchte in %
    
    Returns:
        Taupunkt in °C
    """
    # Magnus-Formel Konstanten
    a = 17.27
    b = 237.7
    
    # Sättigungsdampfdruck berechnen
    alpha = (a * temp_c) / (b + temp_c) + math.log(humidity_percent / 100.0)
    dewpoint = (b * alpha) / (a - alpha)
    
    return round(dewpoint, 1)


def get_solar_adjustment(cloud_cover: float, local_time: datetime, solar_radiation: float = None) -> float:
    """
    Berechnet Sonnenaufschlag basierend auf Tageszeit und Bewölkung
    
    Args:
        cloud_cover: Bewölkung in %
        local_time: Lokale Zeit
        solar_radiation: Globalstrahlung in W/m² (optional)
    
    Returns:
        Temperaturaufschlag in °C
    """
    hour = local_time.hour
    
    # Basis-Sonnenaufschlag nach Tageszeit
    if 11 <= hour <= 13:  # Mittags
        base_adjustment = 4.0
    elif 10 <= hour <= 14:  # Vormittags/Nachmittags
        base_adjustment = 3.0
    elif 9 <= hour <= 15:  # Weitere Tageszeit
        base_adjustment = 2.0
    else:
        base_adjustment = 0.0
    
    # Reduktion durch Bewölkung
    cloud_factor = max(0.0, 1.0 - cloud_cover / 100.0)
    
    # Optional: Anpassung durch Globalstrahlung
    if solar_radiation is not None:
        # Typische Maximalstrahlung ~800 W/m²
        radiation_factor = min(1.0, solar_radiation / 800.0)
        cloud_factor = max(cloud_factor, radiation_factor)
    
    return base_adjustment * cloud_factor


def compute_thermal_humidity_score(weather: WeatherData) -> Tuple[float, str]:
    """
    Berechnet den Thermik-Feuchtigkeits-Score (40% Gewichtung)
    
    Args:
        weather: WeatherData Objekt
        
    Returns:
        Tuple aus (Score, Begründung)
    """
    # Nassbulb-Temperatur berechnen
    wetbulb = compute_wetbulb_temperature(weather.temperature, weather.humidity)
    
    # Sonnenaufschlag hinzufügen
    solar_adj = get_solar_adjustment(weather.cloud_cover, weather.local_time, weather.solar_radiation)
    effective_wetbulb = wetbulb + solar_adj
    
    # Basis-Mapping der Nassbulb-Temperatur
    if effective_wetbulb <= 18:
        base_score = 10.0
    elif effective_wetbulb <= 20:
        base_score = 8.5
    elif effective_wetbulb <= 22:
        base_score = 6.5
    elif effective_wetbulb <= 24:
        base_score = 4.5
    elif effective_wetbulb <= 26:
        base_score = 2.5
    else:
        base_score = 0.5
    
    # Wind-Malus bei hohen Temperaturen
    wind_penalty = 0.0
    reason_parts = [f"Nassbulb {effective_wetbulb:.1f}°C"]
    
    if weather.wind_speed < 1.0 and effective_wetbulb >= 22:
        wind_penalty += 2.0
        reason_parts.append("Nullwind-Malus -2")
    
    # Dauer-Malus bei sehr hohen Temperaturen
    duration_penalty = 0.0
    if effective_wetbulb >= 24 and weather.duration_minutes > 60:
        extra_hours = (weather.duration_minutes - 60) // 60
        duration_penalty = min(3.0, extra_hours * 1.0)
        reason_parts.append(f"Dauer-Malus -{duration_penalty}")
    
    final_score = max(0.0, min(10.0, base_score - wind_penalty - duration_penalty))
    reason = f"Thermik: {', '.join(reason_parts)} = {final_score:.1f}"
    
    return final_score, reason


def compute_precipitation_score(weather: WeatherData) -> Tuple[float, str]:
    """
    Berechnet den Niederschlags-Score (35% Gewichtung)
    
    Args:
        weather: WeatherData Objekt
        
    Returns:
        Tuple aus (Score, Begründung)
    """
    # Basis-Score basierend auf Niederschlagsrate
    rate = weather.precipitation_rate
    
    if rate == 0:
        rate_score = 10.0
    elif rate <= 0.5:
        rate_score = 7.0
    elif rate <= 1.0:
        rate_score = 5.0
    elif rate <= 2.0:
        rate_score = 2.5
    else:
        rate_score = 0.5
    
    # PoP-Faltung
    pop = weather.precipitation_prob / 100.0
    folded_score = (1 - pop) * 10.0 + pop * rate_score
    
    reason_parts = [f"Rate {rate:.1f}mm/h, PoP {weather.precipitation_prob:.0f}%"]
    
    # Matschflag (Regen letzte 24h)
    matsch_penalty = 0.0
    if weather.precipitation_24h >= 2.0:
        matsch_penalty = 2.0
        reason_parts.append(f"Matsch-Malus -{matsch_penalty}")
    
    # Gewitter-/Hagel-Check (aus Warnungen)
    thunderstorm_cap = 10.0
    for warning in weather.warnings:
        if any(keyword in warning.get('event', '').lower() 
               for keyword in ['gewitter', 'hagel', 'thunder', 'hail']):
            thunderstorm_cap = 2.0
            reason_parts.append("Gewitter-Cap 2.0")
            break
    
    final_score = max(0.0, min(thunderstorm_cap, folded_score - matsch_penalty))
    reason = f"Niederschlag: {', '.join(reason_parts)} = {final_score:.1f}"
    
    return final_score, reason


def compute_wind_score(weather: WeatherData) -> Tuple[float, str]:
    """
    Berechnet den Wind-Score (15% Gewichtung) - U-förmige Kurve
    
    Args:
        weather: WeatherData Objekt
        
    Returns:
        Tuple aus (Score, Begründung)
    """
    wind = weather.wind_speed
    
    # U-förmige Bewertung
    if wind <= 0.5:
        base_score = 3.0
    elif wind <= 1.0:
        base_score = 6.0
    elif wind <= 3.0:
        base_score = 9.5
    elif wind <= 6.0:
        base_score = 8.0
    elif wind <= 8.0:
        base_score = 7.0
    elif wind <= 10.0:
        base_score = 5.0
    elif wind <= 13.0:
        base_score = 3.0
    else:
        base_score = 1.5
    
    # Böen-Malus
    gust_cap = 10.0
    reason_parts = [f"Wind {wind:.1f}m/s"]
    
    if weather.wind_gust >= 20:  # ~8 Bft
        gust_cap = 1.0
        reason_parts.append("Böen ≥8Bft, Cap 1.0")
    elif weather.wind_gust >= 15:  # ~7 Bft
        gust_cap = 3.0
        reason_parts.append("Böen ≥7Bft, Cap 3.0")
    
    final_score = min(gust_cap, base_score)
    reason = f"Wind: {', '.join(reason_parts)} = {final_score:.1f}"
    
    return final_score, reason


def compute_stickiness_score(weather: WeatherData) -> Tuple[float, str]:
    """
    Berechnet den Feuchtekomfort/Stickiness-Score (10% Gewichtung)
    
    Args:
        weather: WeatherData Objekt
        
    Returns:
        Tuple aus (Score, Begründung)
    """
    # Taupunkt berechnen
    dewpoint = compute_dewpoint(weather.temperature, weather.humidity)
    
    # Basis-Mapping des Taupunkts
    if dewpoint <= 12:
        base_score = 10.0
    elif dewpoint <= 16:
        base_score = 8.5
    elif dewpoint <= 18:
        base_score = 6.5
    elif dewpoint <= 20:
        base_score = 4.5
    elif dewpoint <= 22:
        base_score = 2.5
    else:
        base_score = 0.5
    
    reason_parts = [f"Taupunkt {dewpoint:.1f}°C"]
    
    # Nullwind-Malus
    wind_penalty = 0.0
    if weather.wind_speed < 1.0:
        wind_penalty += 2.0
        reason_parts.append("Nullwind-Malus -2")
    
    # Dauer-Malus bei hohem Taupunkt
    duration_penalty = 0.0
    if dewpoint >= 20 and weather.duration_minutes > 60:
        extra_hours = (weather.duration_minutes - 60) // 60
        duration_penalty = min(3.0, extra_hours * 1.0)
        reason_parts.append(f"Dauer-Malus -{duration_penalty}")
    
    final_score = max(0.0, min(10.0, base_score - wind_penalty - duration_penalty))
    reason = f"Stickiness: {', '.join(reason_parts)} = {final_score:.1f}"
    
    return final_score, reason


def apply_weather_warning_caps(base_fsi: float, warnings: List[Dict]) -> Tuple[float, List[str]]:
    """
    Wendet Wetterwarnungs-Caps auf den FSI an
    
    Args:
        base_fsi: Basis-FSI vor Warnungs-Caps
        warnings: Liste der Wetterwarnungen
        
    Returns:
        Tuple aus (angepasster FSI, Liste der angewandten Caps)
    """
    caps_applied = []
    current_fsi = base_fsi
    
    for warning in warnings:
        event = warning.get('event', '').lower()
        severity = warning.get('severity', 'minor').lower()
        
        # Gewitterwarnungen
        if any(keyword in event for keyword in ['gewitter', 'thunder']):
            if severity in ['severe', 'extreme'] or warning.get('level', 1) >= 2:
                current_fsi = 0.0
                caps_applied.append(f"Gewitterwarnung Stufe ≥2 → FSI=0")
                break
            elif severity in ['minor', 'moderate'] or warning.get('level', 1) == 1:
                current_fsi = min(current_fsi, 2.0)
                caps_applied.append(f"Gewittervorwarnung → FSI≤2")
        
        # Starkregen
        elif any(keyword in event for keyword in ['starkregen', 'heavy rain']):
            # Prüfe auf ≥10 mm/h in der Beschreibung
            description = warning.get('description', '').lower()
            if '10' in description or 'mm/h' in description:
                current_fsi = min(current_fsi, 2.0)
                caps_applied.append(f"Starkregenwarnung ≥10mm/h → FSI≤2")
        
        # Hitzewarnung
        elif any(keyword in event for keyword in ['hitze', 'heat', 'heiß']):
            if '32' in warning.get('description', '') or severity in ['severe', 'extreme']:
                current_fsi = min(current_fsi, 2.0)
                caps_applied.append(f"Hitzewarnung >32°C → FSI≤2")
        
        # Sturmwarnungen
        elif any(keyword in event for keyword in ['sturm', 'wind', 'böen']):
            if severity in ['extreme'] or '8' in warning.get('description', ''):
                current_fsi = min(current_fsi, 1.0)
                caps_applied.append(f"Sturmwarnung ≥8Bft → FSI≤1")
            elif severity in ['severe'] or '7' in warning.get('description', ''):
                current_fsi = min(current_fsi, 3.0)
                caps_applied.append(f"Sturmwarnung ≥7Bft → FSI≤3")
    
    return current_fsi, caps_applied


def compute_fsi(weather: WeatherData, detailed: bool = False) -> Dict:
    """
    Hauptfunktion zur FSI-Berechnung
    
    Args:
        weather: WeatherData Objekt
        detailed: Ob detaillierte Ausgabe gewünscht ist
        
    Returns:
        Dictionary mit FSI-Ergebnis und Details
    """
    # Teilscores berechnen
    thermal_score, thermal_reason = compute_thermal_humidity_score(weather)
    precip_score, precip_reason = compute_precipitation_score(weather)
    wind_score, wind_reason = compute_wind_score(weather)
    sticky_score, sticky_reason = compute_stickiness_score(weather)
    
    # Gewichtete Summe
    weighted_fsi = (
        0.40 * thermal_score +
        0.35 * precip_score +
        0.15 * wind_score +
        0.10 * sticky_score
    )
    
    # Auf 0.5 runden
    base_fsi = round(weighted_fsi * 2) / 2
    base_fsi = max(0.0, min(10.0, base_fsi))
    
    # Wetterwarnungs-Caps anwenden
    final_fsi, warning_caps = apply_weather_warning_caps(base_fsi, weather.warnings)
    
    # Begründung zusammenstellen
    reasons = [thermal_reason, precip_reason, wind_reason, sticky_reason]
    if warning_caps:
        reasons.extend(warning_caps)
    
    main_reason = f"FSI={final_fsi} - " + "; ".join(reasons)
    
    result = {
        'fsi': final_fsi,
        'reason': main_reason,
        'timestamp': weather.local_time.isoformat(),
        'location': LOCATION_NAME
    }
    
    if detailed:
        result.update({
            'subscores': {
                'thermal_humidity': {'score': thermal_score, 'weight': 0.40, 'reason': thermal_reason},
                'precipitation': {'score': precip_score, 'weight': 0.35, 'reason': precip_reason},
                'wind': {'score': wind_score, 'weight': 0.15, 'reason': wind_reason},
                'stickiness': {'score': sticky_score, 'weight': 0.10, 'reason': sticky_reason}
            },
            'base_fsi': base_fsi,
            'warnings_applied': warning_caps,
            'weather_data': {
                'temperature': weather.temperature,
                'humidity': weather.humidity,
                'wind_speed': weather.wind_speed,
                'wind_gust': weather.wind_gust,
                'precipitation_prob': weather.precipitation_prob,
                'precipitation_rate': weather.precipitation_rate,
                'precipitation_24h': weather.precipitation_24h,
                'cloud_cover': weather.cloud_cover,
                'wetbulb_temp': compute_wetbulb_temperature(weather.temperature, weather.humidity),
                'dewpoint': compute_dewpoint(weather.temperature, weather.humidity)
            }
        })
    
    return result


# Demo function for fallback - creates realistic Hamburg weather data
def fetch_dwd_weather_data() -> Optional[WeatherData]:
    """
    Fallback function that provides demo weather data for Hamburg
    Used when DWD API is not available
    
    Returns:
        WeatherData object with realistic Hamburg summer weather
    """
    weather = WeatherData()
    weather.temperature = 22.5
    weather.humidity = 65.0
    weather.wind_speed = 2.8
    weather.wind_gust = 4.2
    weather.precipitation_prob = 20.0
    weather.precipitation_rate = 0.0
    weather.precipitation_24h = 0.1
    weather.cloud_cover = 35.0
    weather.solar_radiation = 580.0
    weather.local_time = datetime.now()
    weather.duration_minutes = 120
    weather.warnings = []
    
    logger.info(f"Using demo weather data for {LOCATION_NAME}")
    return weather


if __name__ == "__main__":
    print("🦊 FSI Calculator - Core Module")
    print("Use fsi_cli.py for command-line interface or import for programmatic use")
