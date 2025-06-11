from g4f.client import Client
import config

prompt = config.GPT_PROMPT

def generate(query):
    try:
        client = Client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"{prompt + query}"}],
            web_search=False
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка: {e}")
        return "Произошла ошибка"