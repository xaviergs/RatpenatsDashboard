import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
client = create_client(url, key)

res = client.table("bat_observations").select("id", count="exact").eq("count", 0).eq("buzz", 0).execute()
print("Rows with count=0 and buzz=0:", res.count)
