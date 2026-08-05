# 🦊 Fursuitability Index (FSI) C# Aktuelle FSI für Hamburg berechnen
python fsi_cli.py --dwd

# Detaillierte Ausgabe
python fsi_cli.py --dwd --format detailed

# JSON-Export für APIs
python fsi_cli.py --dwd --format json

# 6-Stunden Vorhersage
python fsi_cli.py --dwd --forecast 6

# 5-Tage FSI Vorhersage mit Plot erstellen
python fsi_plot.py

# Oder mit den bereitgestellten Shell-Scripts:
./fsi_plot.sh    # (Linux/macOS)
fsi_plot.bat     # (Windows)
```in wissenschaftlich fundiertes Python-Tool zur Berechnung des **Fursuitability-Index (FSI)** für die Eurofurence in Hamburg. Der Index bewertet auf einer Skala von 0-10, wie gut die aktuellen Wetterbedingungen für Fursuiting-Aktivitäten geeignet sind.

## 🌟 Features

- **🔬 Wissenschaftlich fundiert**: Basiert auf Nassbulb-Temperatur, Taupunkt und meteorologischen Parametern
- **🌦️ Live-Wetterdaten**: Integration mit DWD OpenData APIs für aktuelle Hamburg-Daten
- **⚖️ Gewichtete Bewertung**: Berücksichtigt verschiedene Faktoren mit wissenschaftlich begründeter Gewichtung
- **⚠️ Wetterwarnungen**: Automatische FSI-Anpassung bei Gewitter-, Sturm-, Hitze- und Starkregen-Warnungen
- **📊 Detaillierte Analyse**: Vollständige Begründung und JSON-Export
- **💻 CLI-Interface**: Einfache Kommandozeilen-Bedienung
- **📈 5-Tage Plots**: Grafische Vorhersage-Visualisierung mit matplotlib

## 🚀 Schnellstart

### Installation

```bash
# Repository klonen
git clone https://github.com/laffiie/EurofurenceWeather.git
cd EurofurenceWeather

# Abhängigkeiten installieren
pip install -r requirements.txt

# Oder automatisches Setup
python setup.py
```

### Sofortige Nutzung

```bash
# Aktueller FSI mit echten Hamburg-Wetterdaten
python fsi_cli.py --dwd

# Detaillierte Ausgabe
python fsi_cli.py --dwd --format detailed

# JSON-Export für APIs
python fsi_cli.py --dwd --format json

# 6-Stunden Vorhersage
python fsi_cli.py --dwd --forecast 6
```

## 📖 Ausführliche Anleitung

### � 5-Tage FSI Forecast Plot

Das System kann eine detaillierte 5-Tage Vorhersage mit grafischer Darstellung erstellen:

```bash
python fsi_plot.py
```

**Der Plot zeigt:**
- 🎯 FSI-Verlauf über 5 Tage mit farbkodierten Zonen:
  - 🟢 Grün (8-10): Perfekte Fursuiting-Bedingungen
  - 🟡 Gelb (6-8): Gute Bedingungen mit leichten Einschränkungen  
  - 🟠 Orange (4-6): Mäßige Bedingungen, Aufmerksamkeit erforderlich
  - 🔴 Rot (0-4): Schwierige Bedingungen, erhöhte Vorsicht
- 🌡️ Temperatur- und Luftfeuchtigkeitsverlauf
- 📊 Zusammenfassende Statistiken
- 🕐 Alle 6 Stunden aktualisiert (4 Datenpunkte pro Tag)

**Ausgabe:** Speichert den Plot als `fsi_forecast.png` im aktuellen Verzeichnis.

### �🛠️ Installation und Setup

#### Voraussetzungen
- Python 3.7 oder höher
- Internetverbindung für Live-Wetterdaten

#### Schritt-für-Schritt Installation

1. **Repository herunterladen:**
   ```bash
   git clone https://github.com/laffiie/EurofurenceWeather.git
   cd EurofurenceWeather
   ```

2. **Automatisches Setup (empfohlen):**
   ```bash
   python setup.py
   ```
   
   Oder manuell:
   ```bash
   pip install -r requirements.txt
   ```

3. **Installation testen:**
   ```bash
   python fsi_cli.py --demo
   ```

### 🎯 Nutzung

#### Kommandozeilen-Interface (CLI)

**Grundlegende Befehle:**

```bash
# Live-Daten vom DWD (empfohlen)
python fsi_cli.py --dwd

# Demo-Daten für Tests
python fsi_cli.py --demo

# Manuelle Eingabe
python fsi_cli.py --manual
```

**Ausgabeformate:**

```bash
# Kompakte Ausgabe (Standard)
python fsi_cli.py --dwd --format compact

# Detaillierte Analyse
python fsi_cli.py --dwd --format detailed

# JSON für APIs/Weiterverarbeitung
python fsi_cli.py --dwd --format json
```

**Vorhersagen:**

```bash
# 3 Stunden Vorhersage
python fsi_cli.py --dwd --forecast 3

# 12 Stunden Vorhersage
python fsi_cli.py --dwd --forecast 12
```

**Erweiterte Optionen:**

```bash
# Andere DWD-Station (Beispiel)
python fsi_cli.py --dwd --station 10384

# Eigene Konfigurationsdatei
python fsi_cli.py --dwd --config my_config.json

# Stumme Ausgabe (nur Ergebnis)
python fsi_cli.py --dwd --quiet
```

#### Shell-Skripte (Unix/Linux/macOS)

```bash
# Ausführbar machen
chmod +x fsi.sh

# FSI direkt abrufen
./fsi.sh
```

#### Windows Batch-Datei

```cmd
fsi.bat
```

### 📊 Beispiel-Ausgaben

#### Kompakte Ausgabe
```
🦊 Fursuitability Index: 8.5/10
📅 2025-08-24T15:30:00
📍 Hamburg
🎭 Bewertung: 🟢 Ausgezeichnet für Fursuiting!
```

#### Detaillierte Analyse
```
🦊 Fursuitability Index: 8.5/10
📅 2025-08-24T15:30:00
📍 Hamburg
📝 FSI=8.5 - Thermik: Nassbulb 16.2°C = 9.0; Niederschlag: Rate 0.0mm/h, PoP 10% = 10.0; 
Wind: Wind 2.1m/s, optimal = 10.0; Stickiness: Taupunkt 12.1°C = 8.0

📊 Detailbewertung:
  • Thermal Humidity: 9.0/10 (40%)
  • Precipitation: 10.0/10 (35%)  
  • Wind: 10.0/10 (15%)
  • Stickiness: 8.0/10 (10%)

🌡️ Wetterdaten:
  • Temperatur: 18.5°C
  • Nassbulb-Temperatur: 16.2°C
  • Luftfeuchtigkeit: 72%
  • Wind: 2.1 m/s
  • Niederschlag: 0%

🎭 Bewertung: 🟢 Ausgezeichnet für Fursuiting!
```

#### JSON-Export
```json
{
  "fsi": 8.5,
  "timestamp": "2025-08-24T15:30:00",
  "location": "Hamburg",
  "subscores": {
    "thermal_humidity": {"score": 9.0, "weight": 0.4},
    "precipitation": {"score": 10.0, "weight": 0.35},
    "wind": {"score": 10.0, "weight": 0.15},
    "stickiness": {"score": 8.0, "weight": 0.1}
  },
  "weather_data": {
    "temperature": 18.5,
    "wetbulb_temp": 16.2,
    "humidity": 72.0
  }
}
```

### ⚙️ Konfiguration

Die `config.json` kann angepasst werden:

```json
{
  "location": {
    "name": "Hamburg",
    "lat": 53.561337,
    "lon": 9.986310
  },
  "dwd": {
    "station_id": "10147"
  },
  "fsi_thresholds": {
    "excellent": 8.0,
    "good": 6.0,
    "fair": 4.0,
    "poor": 2.0
  }
}
```

## 📚 Wissenschaftliche Grundlagen

### 🎯 Bewertungslogik

Der FSI basiert auf vier gewichteten Faktoren:

| Faktor | Gewicht | Berechnung |
|--------|---------|------------|
| **Thermik/Feuchte** | 40% | Nassbulb-Temperatur + Sonnenaufschlag |
| **Niederschlag** | 35% | Regenrate, Wahrscheinlichkeit, 24h-Summe |
| **Wind** | 15% | U-förmige Bewertung (optimal: 1-3 m/s) |
| **Klebrigkeit** | 10% | Taupunkt-basierter Feuchtekomfort |

### 🌡️ Temperatur-Bewertung (Nassbulb + Sonne)

- **≤18°C**: 10 Punkte (optimal) - Sehr angenehm
- **18-20°C**: 8-9 Punkte (sehr gut) - Komfortabel  
- **20-22°C**: 6-7 Punkte (gut) - Noch angenehm
- **22-24°C**: 4-5 Punkte (mäßig) - Etwas warm
- **24-26°C**: 2-3 Punkte (schlecht) - Zu warm
- **>26°C**: 0-1 Punkte (kritisch) - Gefährlich

### ⚠️ Wetterwarnungs-Caps

- **Gewitter ≥Stufe 2**: FSI = 0 (Sicherheitsrisiko)
- **Starkregen ≥Stufe 2**: FSI = max(2, original_fsi/2)
- **Sturm ≥Stufe 3**: FSI = max(1, original_fsi/3)
- **Hitzewarnung**: FSI = max(3, original_fsi/2)

### 🔬 Formeln

**Nassbulb-Temperatur** (Stull-Approximation):
```
T_wb = T × atan(0.151977×√(RH+8.313659)) + atan(T+RH) - atan(RH-1.676331) + 0.00391838×(RH^1.5)×atan(0.023101×RH) - 4.686035
```

**Taupunkt** (Magnus-Formel):
```
T_d = (237.7 × ln(RH/100) + 17.27×T) / (17.27 - ln(RH/100) - 17.27×T/(237.7+T))
```

## 🔧 Entwicklung

### Programmatische Nutzung

```python
from fsi_calculator import compute_fsi, WeatherData
from dwd_integration import create_weather_from_dwd

# Live-Daten laden
weather = create_weather_from_dwd()

# FSI berechnen
result = compute_fsi(weather, detailed=True)

print(f"FSI: {result['fsi']}/10")
```

### Projektstruktur

```
EurofurenceWeather/
├── fsi_calculator.py      # Kern-Algorithmus
├── fsi_cli.py            # Kommandozeilen-Interface  
├── dwd_integration.py    # DWD-API Integration
├── config.json          # Konfiguration
├── requirements.txt     # Python-Abhängigkeiten
├── setup.py            # Installations-Skript
├── test_fsi.py         # Unit-Tests
├── fsi.sh / fsi.bat    # Shell-Skripte
└── README.md          # Diese Dokumentation
```

### Tests ausführen

```bash
python test_fsi.py
```

## 🤝 Beitragen

1. Fork das Repository
2. Feature-Branch erstellen (`git checkout -b feature/AmazingFeature`)
3. Änderungen committen (`git commit -m 'Add AmazingFeature'`)
4. Branch pushen (`git push origin feature/AmazingFeature`)
5. Pull Request erstellen

## 📄 Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe `LICENSE` für Details.

## 🙏 Danksagungen

- **DWD (Deutscher Wetterdienst)** für die kostenlosen OpenData-APIs
- **Eurofurence Convention** für die Inspiration
- **Furry-Community** für das Feedback zur FSI-Logik

## 📞 Support

Bei Fragen oder Problemen:
- GitHub Issues: [Issues](https://github.com/laffiie/EurofurenceWeather/issues)
- Email: [dein-email@example.com]

---

**Viel Spaß beim Fursuiting in Hamburg! 🦊🌦️**
- Gewitter Stufe 1: FSI ≤ 2
- Starkregen ≥10mm/h: FSI ≤ 2  
- Hitze >32°C: FSI ≤ 2
- Sturm ≥8 Bft: FSI ≤ 1
- Sturm ≥7 Bft: FSI ≤ 3

## Installation

```bash
# Repository klonen
git clone https://github.com/laffiie/EurofurenceWeather
cd EurofurenceWeather

# Abhängigkeiten installieren
pip install -r requirements.txt
```

## Verwendung

### Basis-Verwendung
```bash
python fsi_calculator.py
```

### Programmatische Verwendung
```python
from fsi_calculator import WeatherData, compute_fsi
from datetime import datetime

# Wetterdaten erstellen
weather = WeatherData()
weather.temperature = 24.5
weather.humidity = 68.0
weather.wind_speed = 2.3
weather.local_time = datetime.now()

# FSI berechnen
result = compute_fsi(weather, detailed=True)
print(f"FSI: {result['fsi']}/10")
print(f"Begründung: {result['reason']}")
```

### Tests ausführen
```bash
python test_fsi.py
```

## Beispiel-Ausgabe

```
🦊 Fursuitability Index (FSI) Calculator für Eurofurence
============================================================

📊 FSI-Ergebnis für Hamburg:
🎯 Fursuitability Index: 6.0/10
📝 Begründung: FSI=6.0 - Thermik: Nassbulb 21.2°C = 6.5; Niederschlag: Rate 0.0mm/h, PoP 15% = 9.2; Wind: Wind 2.3m/s = 9.5; Stickiness: Taupunkt 17.8°C = 6.5

📈 Detaillierte Bewertung:
  • Thermal Humidity: 6.5/10 (Gewicht: 40%)
  • Precipitation: 9.2/10 (Gewicht: 35%)
  • Wind: 9.5/10 (Gewicht: 15%)
  • Stickiness: 6.5/10 (Gewicht: 10%)

🎭 Empfehlung: 🟡 Gut geeignet mit kleinen Einschränkungen
```

## API-Integration

Das Skript ist vorbereitet für die Integration mit:
- **DWD MOSMIX**: Wettervorhersage
- **DWD ICON-D2**: Hochauflösende Vorhersage
- **DWD WarnWetter-API**: Aktuelle Wetterwarnungen

Die Implementierung der vollständigen API-Anbindung ist als Erweiterung geplant.

## Wissenschaftliche Grundlagen

- **Nassbulb-Temperatur**: Stull-Approximation für gefühlte Temperatur unter Berücksichtigung der Luftfeuchtigkeit
- **Taupunkt**: Magnus-Formel für Feuchtekomfort-Bewertung
- **Sonnenaufschlag**: Zeitabhängige Temperaturkorrektur basierend auf Bewölkung
- **Windchill**: U-förmige Bewertung optimal für Fursuit-Belüftung

## Lizenz

MIT License - siehe [LICENSE](LICENSE) Datei.

## Beitrag

Verbesserungsvorschläge und Pull Requests sind willkommen! Besonders:
- Vollständige DWD-API-Integration
- Zusätzliche Wetterparameter
- UI/Web-Interface
- Historische Datenauswertung
