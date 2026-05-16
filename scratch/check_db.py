import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
client = create_client(url, key)

# Let's try to query bat_observations or bat_observations_full
try:
    res = client.table("bat_observations_full").select("*").limit(1).execute()
    print("bat_observations_full:", res.data[0] if res.data else "empty")
except Exception as e:
    print(e)

try:
    res = client.table("bat_observations").select("*").limit(1).execute()
    print("bat_observations:", res.data[0] if res.data else "empty")
except Exception as e:
    print(e)
