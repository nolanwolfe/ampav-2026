"""
Run ONCE to register your S700 with Stripe.

Steps on the S700 device:
  Settings (gear icon) > Device > Generate pairing code
  — you'll get an 8-character code like "SWIFTONE"
"""
import os
import sys
from dotenv import load_dotenv
import stripe

load_dotenv()
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

print("=== Stripe S700 Registration ===\n")

# EU/France requires a Location for compliance
print("Step 1: Create a Location (required for EU terminals)")
city = input("  City (e.g. Paris): ").strip()
line1 = input("  Street address: ").strip()
postal = input("  Postal code: ").strip()

location = stripe.terminal.Location.create(
    display_name=f"{city} POS",
    address={
        "line1": line1,
        "city": city,
        "postal_code": postal,
        "country": "FR",
    },
)
print(f"  Location created: {location.id}\n")

# Register the reader
print("Step 2: Enter the registration code shown on your S700")
print("  On the S700: Settings > Device > Generate pairing code")
code = input("  Registration code: ").strip()
label = input("  Label (e.g. 'France POS 1') [France POS]: ").strip() or "France POS"

reader = stripe.terminal.Reader.create(
    registration_code=code,
    label=label,
    location=location.id,
)

print(f"\n=== Reader Registered ===")
print(f"  ID:       {reader.id}")
print(f"  Label:    {reader.label}")
print(f"  Status:   {reader.status}")
print(f"  Location: {location.id}")
print(f"\nAdd this to your .env file:")
print(f"  READER_ID={reader.id}")
