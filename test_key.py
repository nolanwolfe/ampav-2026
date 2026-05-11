import stripe, os
from dotenv import load_dotenv
load_dotenv()
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
acct = stripe.Account.retrieve()
print("Key valid! Account:", acct.id, "|", acct.country)
