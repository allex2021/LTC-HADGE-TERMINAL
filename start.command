#!/bin/bash
cd "$(dirname "$0")"
echo "=================================================="
echo "🚀 Starting Cyber2 Hedge Terminal Backend..."
echo "=================================================="
echo "Port: 8000"
echo "Please keep this terminal window open while trading."
echo "=================================================="
python3 server.py
