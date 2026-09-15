from google import genai
client = genai.Client()
for m in client.models.list():
    if "flash" in m.name or "pro" in m.name:
        print(m.name)
