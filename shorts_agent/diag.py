"""python -m shorts_agent.diag <model>  : plain call vs grounded call, to isolate a 429."""
import os, sys
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
model = sys.argv[1]
c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
grounded = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
for name, cfg in [("plain", None), ("grounded", grounded)]:
    try:
        r = c.models.generate_content(model=model, contents="In one sentence: boiling point of water at sea level?", config=cfg)
        print(name, "OK:", (r.text or "")[:80])
    except Exception as e:
        print(name, "FAILED:", type(e).__name__, str(e)[:160])