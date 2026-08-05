#!/bin/bash
# Fursuitability Index - Quick Access Script
cd "$(dirname "$0")"
python3 fsi_cli.py --dwd "$@"
