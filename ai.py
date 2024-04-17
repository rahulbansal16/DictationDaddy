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
            {"role": "system", "content": "Please follow user instructions do not do anything extra. If you are unsure of what to do return the user input."},
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

