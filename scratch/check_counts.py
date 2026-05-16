import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
client = create_client(url, key)

res = client.table("bat_observations").select("count, buzz").limit(100).execute()
counts = [r["count"] for r in res.data]
buzzes = [r["buzz"] for r in res.data]
print("Max count in sample:", max(counts) if counts else 0)
print("Max buzz in sample:", max(buzzes) if buzzes else 0)

# Check distinct counts
res2 = client.table("bat_observations").select("count").limit(1000).execute()
print("Distinct counts in 1000 sample:", set([r["count"] for r in res2.data]))
