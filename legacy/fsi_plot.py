#!/usr/bin/env python3
"""
FSI Forecast Plot Generator

Creates a visual plot showing the Fursuitability Index forecast for the next 5 days.
Displays FSI values, weather conditions, and provides recommendations for fursuiting.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta, timezone
import numpy as np
import argparse
import sys
from typing import List, Dict, Optional

from fsi_calculator import compute_fsi, WeatherData
from dwd_integration import create_weather_from_dwd, load_config_for_dwd

# Plot styling
plt.style.use('default')
COLORS = {
    'excellent': '#2E8B57',    # Sea Green
    'good': '#32CD32',         # Lime Green  
    'fair': '#FFD700',         # Gold
    'poor': '#FF8C00',         # Dark Orange
    'critical': '#DC143C'      # Crimson
}

def get_fsi_color(fsi_value: float) -> str:
    """Returns color based on FSI value"""
    if fsi_value >= 8.0:
        return COLORS['excellent']
    elif fsi_value >= 6.0:
        return COLORS['good']
    elif fsi_value >= 4.0:
        return COLORS['fair']
    elif fsi_value >= 2.0:
        return COLORS['poor']
    else:
        return COLORS['critical']

def get_fsi_label(fsi_value: float) -> str:
    """Returns descriptive label for FSI value"""
    if fsi_value >= 8.0:
        return "Ausgezeichnet"
    elif fsi_value >= 6.0:
        return "Gut"
    elif fsi_value >= 4.0:
        return "Mäßig"
    elif fsi_value >= 2.0:
        return "Schlecht"
    else:
        return "Kritisch"

def fetch_forecast_data(hours: int = 120, station_id: str = "10147") -> List[Dict]:
    """
    Fetches FSI forecast data for specified hours
    
    Args:
        hours: Number of hours to forecast (default: 120 = 5 days)
        station_id: DWD station ID
        
    Returns:
        List of dictionaries with timestamp, weather, and FSI data
    """
    config = load_config_for_dwd()
    forecast_data = []
    
    print(f"📊 Lade {hours}h-Vorhersage für Hamburg...")
    
    # Sample every 6 hours for 5-day forecast
    sample_hours = list(range(0, hours + 1, 6))
    
    for hour in sample_hours:
        try:
            # Get weather data for this hour
            weather = create_weather_from_dwd(station_id, hour, config)
            
            if weather:
                # Calculate FSI
                fsi_result = compute_fsi(weather, detailed=True)
                
                if fsi_result:
                    forecast_data.append({
                        'timestamp': weather.local_time,
                        'hour_offset': hour,
                        'weather': weather,
                        'fsi_result': fsi_result,
                        'fsi': fsi_result['fsi'],
                        'temperature': weather.temperature,
                        'humidity': weather.humidity,
                        'wind_speed': weather.wind_speed,
                        'precipitation_prob': weather.precipitation_prob,
                        'precipitation_rate': weather.precipitation_rate
                    })
                    
                    print(f"  ✅ +{hour:3d}h: FSI {fsi_result['fsi']:.1f}/10 - T={weather.temperature:.1f}°C")
                else:
                    print(f"  ❌ +{hour:3d}h: FSI-Berechnung fehlgeschlagen")
            else:
                print(f"  ❌ +{hour:3d}h: Keine Wetterdaten")
                
        except Exception as e:
            print(f"  ⚠️  +{hour:3d}h: Fehler - {e}")
            continue
    
    print(f"📈 {len(forecast_data)} Datenpunkte geladen")
    return forecast_data

def create_fsi_plot(forecast_data: List[Dict], output_file: str = "fsi_forecast.png", 
                   show_details: bool = True) -> str:
    """
    Creates FSI forecast plot
    
    Args:
        forecast_data: List of forecast data points
        output_file: Output filename
        show_details: Whether to show detailed weather info
        
    Returns:
        Path to created plot file
    """
    if not forecast_data:
        raise ValueError("Keine Vorhersagedaten verfügbar")
    
    # Setup the plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), height_ratios=[2, 1])
    fig.suptitle('🦊 Fursuitability Index - 5-Tage Vorhersage Hamburg', fontsize=16, fontweight='bold')
    
    # Extract data
    timestamps = [d['timestamp'] for d in forecast_data]
    fsi_values = [d['fsi'] for d in forecast_data]
    temperatures = [d['temperature'] for d in forecast_data]
    humidity = [d['humidity'] for d in forecast_data]
    wind_speeds = [d['wind_speed'] for d in forecast_data]
    precip_probs = [d['precipitation_prob'] for d in forecast_data]
    
    # Convert timezone-aware datetimes to naive for plotting
    plot_timestamps = [ts.replace(tzinfo=None) if ts.tzinfo else ts for ts in timestamps]
    
    # Main FSI plot
    colors = [get_fsi_color(fsi) for fsi in fsi_values]
    
    # FSI line plot with colored segments
    ax1.plot(plot_timestamps, fsi_values, linewidth=3, alpha=0.8, color='#1f77b4', marker='o', markersize=6)
    
    # Color segments based on FSI value
    for i in range(len(plot_timestamps)-1):
        segment_color = get_fsi_color(fsi_values[i])
        ax1.plot([plot_timestamps[i], plot_timestamps[i+1]], 
                [fsi_values[i], fsi_values[i+1]], 
                color=segment_color, linewidth=4, alpha=0.7)
    
    # FSI zones background
    ax1.axhspan(8, 10, alpha=0.1, color=COLORS['excellent'], label='Ausgezeichnet (8-10)')
    ax1.axhspan(6, 8, alpha=0.1, color=COLORS['good'], label='Gut (6-8)')
    ax1.axhspan(4, 6, alpha=0.1, color=COLORS['fair'], label='Mäßig (4-6)')
    ax1.axhspan(2, 4, alpha=0.1, color=COLORS['poor'], label='Schlecht (2-4)')
    ax1.axhspan(0, 2, alpha=0.1, color=COLORS['critical'], label='Kritisch (0-2)')
    
    # Add FSI value labels on points
    for i, (ts, fsi) in enumerate(zip(plot_timestamps, fsi_values)):
        if i % 2 == 0:  # Show every other label to avoid crowding
            ax1.annotate(f'{fsi:.1f}', (ts, fsi), textcoords="offset points", 
                        xytext=(0,10), ha='center', fontsize=9, fontweight='bold')
    
    ax1.set_ylabel('Fursuitability Index', fontsize=12, fontweight='bold')
    ax1.set_ylim(0, 10)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='lower right', fontsize=10)
    
    # Weather details subplot
    ax2_temp = ax2
    ax2_wind = ax2.twinx()
    
    # Temperature
    temp_line = ax2_temp.plot(plot_timestamps, temperatures, color='red', linewidth=2, 
                             marker='s', markersize=4, label='Temperatur (°C)')
    
    # Wind speed  
    wind_line = ax2_wind.plot(plot_timestamps, wind_speeds, color='blue', linewidth=2, 
                             marker='^', markersize=4, label='Wind (m/s)')
    
    # Precipitation probability as bars
    precip_bars = ax2_temp.bar(plot_timestamps, [p/10 for p in precip_probs], 
                              alpha=0.3, color='lightblue', width=0.1, 
                              label='Niederschlag (%/10)')
    
    ax2_temp.set_ylabel('Temperatur (°C) / Regen (%/10)', fontsize=10)
    ax2_wind.set_ylabel('Wind (m/s)', fontsize=10, color='blue')
    ax2_temp.grid(True, alpha=0.3)
    
    # Combine legends
    lines1, labels1 = ax2_temp.get_legend_handles_labels()
    lines2, labels2 = ax2_wind.get_legend_handles_labels()
    ax2_temp.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=9)
    
    # Format x-axis
    for ax in [ax1, ax2_temp]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m\n%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center')
    
    ax2_temp.set_xlabel('Datum / Uhrzeit', fontsize=10)
    
    # Add current time indicator
    now = datetime.now()
    for ax in [ax1, ax2_temp]:
        ax.axvline(now, color='red', linestyle='--', alpha=0.7, linewidth=2, label='Jetzt')
    
    # Add summary text
    if forecast_data:
        min_fsi = min(fsi_values)
        max_fsi = max(fsi_values)
        avg_fsi = sum(fsi_values) / len(fsi_values)
        
        summary_text = f"📊 5-Tage Zusammenfassung: Min FSI {min_fsi:.1f} | Max FSI {max_fsi:.1f} | Ø {avg_fsi:.1f}"
        fig.text(0.5, 0.02, summary_text, ha='center', fontsize=11, fontweight='bold')
    
    plt.tight_layout()
    plt.subplots_adjust(top=0.93, bottom=0.08)
    
    # Save plot
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"📊 Plot gespeichert: {output_file}")
    
    return output_file

def create_summary_table(forecast_data: List[Dict]) -> str:
    """Creates a text summary of the forecast"""
    if not forecast_data:
        return "Keine Daten verfügbar"
    
    summary = "🦊 FSI 5-Tage Vorhersage - Hamburg\n"
    summary += "=" * 60 + "\n\n"
    
    current_day = None
    day_data = []
    
    for data in forecast_data:
        ts = data['timestamp']
        day = ts.strftime('%A, %d.%m.%Y') if hasattr(ts, 'strftime') else str(ts)[:10]
        time = ts.strftime('%H:%M') if hasattr(ts, 'strftime') else str(ts)[11:16]
        
        if current_day != day:
            if day_data:
                # Summarize previous day
                day_fsi_values = [d['fsi'] for d in day_data]
                avg_fsi = sum(day_fsi_values) / len(day_fsi_values)
                max_fsi = max(day_fsi_values)
                min_fsi = min(day_fsi_values)
                
                summary += f"  Tageswerte: Ø {avg_fsi:.1f} | Max {max_fsi:.1f} | Min {min_fsi:.1f}\n\n"
            
            current_day = day
            day_data = []
            summary += f"📅 {day}\n"
            summary += "-" * 40 + "\n"
        
        fsi = data['fsi']
        temp = data['temperature']
        hum = data['humidity']
        wind = data['wind_speed']
        rain = data['precipitation_prob']
        
        emoji = "🟢" if fsi >= 8 else "🟡" if fsi >= 6 else "🟠" if fsi >= 4 else "🔴" if fsi >= 2 else "⛔"
        
        summary += f"{time}: FSI {fsi:.1f}/10 {emoji} | {temp:.1f}°C | {hum:.0f}% | {wind:.1f}m/s | {rain:.0f}% Regen\n"
        day_data.append(data)
    
    # Final day summary
    if day_data:
        day_fsi_values = [d['fsi'] for d in day_data]
        avg_fsi = sum(day_fsi_values) / len(day_fsi_values)
        max_fsi = max(day_fsi_values)
        min_fsi = min(day_fsi_values)
        summary += f"  Tageswerte: Ø {avg_fsi:.1f} | Max {max_fsi:.1f} | Min {min_fsi:.1f}\n\n"
    
    return summary

def main():
    """Main function for command-line usage"""
    parser = argparse.ArgumentParser(description='FSI 5-Tage Vorhersage Plot Generator')
    parser.add_argument('--hours', type=int, default=120, 
                       help='Vorhersagestunden (Standard: 120 = 5 Tage)')
    parser.add_argument('--output', '-o', default='fsi_forecast.png',
                       help='Ausgabedatei für Plot (Standard: fsi_forecast.png)')
    parser.add_argument('--station', default='10147',
                       help='DWD Station ID (Standard: 10147 = Hamburg)')
    parser.add_argument('--show-summary', action='store_true',
                       help='Zeige Textzusammenfassung')
    parser.add_argument('--no-plot', action='store_true',
                       help='Nur Daten laden, keinen Plot erstellen')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Reduzierte Ausgabe')
    
    args = parser.parse_args()
    
    try:
        # Load forecast data
        if not args.quiet:
            print("🦊 FSI 5-Tage Vorhersage Generator")
            print("=" * 50)
        
        forecast_data = fetch_forecast_data(args.hours, args.station)
        
        if not forecast_data:
            print("❌ Keine Vorhersagedaten verfügbar!")
            sys.exit(1)
        
        # Create plot
        if not args.no_plot:
            plot_file = create_fsi_plot(forecast_data, args.output)
            if not args.quiet:
                print(f"✅ Plot erstellt: {plot_file}")
        
        # Show summary
        if args.show_summary or args.no_plot:
            summary = create_summary_table(forecast_data)
            print(summary)
        
        if not args.quiet:
            print("\n🎭 Viel Spaß beim Fursuiting! 🦊")
            
    except KeyboardInterrupt:
        print("\n⚠️ Abgebrochen")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Fehler: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
