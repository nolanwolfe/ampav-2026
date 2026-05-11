#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "==> Setting up Stripe POS..."

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo ""
echo "==> Done. Next steps:"
echo "  1. Edit .env — paste your Stripe secret key"
echo "  2. Run:  source venv/bin/activate && python setup_reader.py"
echo "  3. Add READER_ID to .env"
echo "  4. Run:  python app.py"
echo "  5. Open: http://localhost:5000"
