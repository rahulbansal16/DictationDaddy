import os
import pyaudio
import houndify
import keyboard
from dotenv import load_dotenv

# Load environment variables
if os.path.exists('local.env'):
    load_dotenv('local.env')
else:
    load_dotenv()

# Audio recording parameters
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 8000

# Initialize PyAudio
audio = pyaudio.PyAudio()

# Houndify client credentials
client_id = os.getenv("HOUNDIFY_CLIENT_ID")
client_key = os.getenv("HOUNDIFY_CLIENT_KEY")
user_id = "test_user"

class MyListener(houndify.HoundListener):
    def onPartialTranscript(self, transcript):
        print("Partial transcript: ", transcript)

    def onFinalResponse(self, response):
        print("Final response: ", response)

    def onError(self, err):
        print("Error: ", err)

    def onFinalPartialTranscript(self, transcript):
        print("The Final Partial transcript", transcript)
        return

    def onPartialTranscriptRaw(self, response):
        print("The PartialTranscriptRaw response is", response)
        return
  
    def onFinalPartialTranscriptProperties(self, transcript, props):
        print("The Final Partial transcript", transcript, props)
        return
  
    def onPartialTranscriptProperties(self, transcript, props):
        print("The Partial transcript", transcript, props)

def listen_from_mic():
    # Setup Houndify client
    client = houndify.StreamingHoundClient(client_id, client_key, user_id, sampleRate=RATE, requestInfo={
        "PartialTranscriptsDesired": True,
        "ReturnResponseAudioAsURL": True,
        "UseFormattedTranscriptionAsDefault": True
    })
    client.setSampleRate(RATE)
    client.start(MyListener())

    # Start recording from microphone
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print("Listening...")

    try:
        while True:
            data = stream.read(CHUNK)
            if not client.fill(data):
                continue
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()
        client.finish()

if __name__ == "__main__":
    listen_from_mic()