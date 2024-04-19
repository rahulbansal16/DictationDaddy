import openai
import os
from dotenv import load_dotenv
if os.path.exists('local.env'):
    load_dotenv('local.env')
else:
    load_dotenv()

openai.api_key = os.getenv("OPENAI_KEY")

# completion = client.chat.completions.create(
#   model="gpt-3.5-turbo",
#   messages=[
#     {"role": "system", "content": "You are a poetic assistant, skilled in explaining complex programming concepts with creative flair."},
#     {"role": "user", "content": "Compose a poem that explains the concept of recursion in programming."}
#   ]
# )

def callGPT(user_input):
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system", 
                "content": 
"""
You are text editor GPT.
You will be given input in the format text command.
You must edit the text based on the command. 
Return only the text.
If there is no command return the text directly without modifying.
Do not return anything extra
Do not try to correct the text for spelling, grammar, punctuation, etc.
If there is no text return the result of command.
Here are few examples
Example 1
input: 'Hello how are you? delete hello'
output: 'how are you?'
Example 2
input: 'Hello how are you? delete last word'
output: 'Hello how are'
Example 3
input: 'Hello how are you? make the H capital for how'
output: 'Hello How are you?'
Example 4
input: 'Quick brown fox jumps over the lazy dog? Make it uppercase'
output: 'QUICK BROWN FOX JUMPS OVER THE LAZY DOG?'
Example 5
input: 'Hello how are you? Quick brown fox jumps over the lazy dog? Make it uppercase and add a question mark'
output: 'Hello how are you? QUICK BROWN FOX JUMPS OVER THE LAZY DOG?'
Example 6
input: 'Hello how are you? Quick brown fox jumps over the lazy dog? delete everything'
output: 
Example 7
input: 'Hello how are you? Quick brown fox jumps over the lazy dog? delete last sentence'
output: 'Hello how are you?'
Example 8
input: 'Hellow how are you?'
output: 'Hellow how are you?'
"""
            },
            {"role": "user", "content": user_input}
        ]
    )
    return completion.choices[0].message.content


def callVisionGPT(base64_image, prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    },
                ],
            }
        ],
        max_tokens=300,
    )
    return response.choices[0].message.content

# print(callGPT())


if __name__ == "__main__":
    print(callGPT("Who is the powerful person in the world?"))

