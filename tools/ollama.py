import requests
import json
url = 'http://192.168.2.234:11434/api/chat'
data = """
{
    "model": "llama3.1",
    "messages": [
        {
            "role": "user",
            "content": "why is the sky blue?"
        }
    ],
    "stream": false
}

"""

response = requests.post(url,  json=json.loads(data))

# Print the response from the server
print( "请求信息:\n" + json.dumps(response.json(), indent=4, ensure_ascii=False))
