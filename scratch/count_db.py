import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
client = create_client(url, key)

res = client.table("bat_observations").select("count", count="exact").limit(1).execute()
print("bat_observations count:", res.count)
