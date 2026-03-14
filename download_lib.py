import requests

url = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"
print(f"Downloading {url}...")

try:
    response = requests.get(url, timeout=30)
    if response.status_code == 200:
        with open("supabase.min.js", "w", encoding="utf-8") as f:
            f.write(response.text)
        print("Success: Saved to supabase.min.js")
    else:
        print(f"Failed: Status {response.status_code}")
except Exception as e:
    print(f"Error: {e}")
