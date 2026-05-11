import stripe, os
from dotenv import load_dotenv
load_dotenv()
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
readers = stripe.terminal.Reader.list()
for r in readers.data:
    print(r.id, "|", r.label, "|", r.status)
