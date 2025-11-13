from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/linkcampus/Desktop/Internship/1st_mvp/law_chatbot/llex/llex_backend/.env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), project=os.getenv("OPENAI_PROJECT_ID"))
print(client.models.list().data[0].id)
