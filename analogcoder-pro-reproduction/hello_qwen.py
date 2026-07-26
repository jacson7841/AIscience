import os

from openai import OpenAI


client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    max_retries=0,
    timeout=120.0,
)

completion = client.chat.completions.create(
    model="qwen3.7-plus",
    messages=[
        {"role": "user", "content": "Hello! Tell me a fun fact about AI."}
    ],
)

print(completion.choices[0].message.content)
