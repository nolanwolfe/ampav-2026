#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
pip install -q gunicorn
exec gunicorn -w 2 -b 0.0.0.0:5000 app:app
