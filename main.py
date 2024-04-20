import pyaudio
import argparse
import asyncio
import aiohttp
import json
import os
import sys
import wave
import websockets
import keyboard
import houndify

import threading
import signal

from datetime import datetime
from dotenv import load_dotenv
from ai import callGPT, callVisionGPT
from consts import TranscriptType

from util import save_frames_and_transcription, save_frames_to_file, take_screenshot
if os.path.exists('local.env'):
    load_dotenv('local.env')
else:
    load_dotenv()

startTime = datetime.now()

all_mic_data = []
all_transcripts = [""]

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 8000

audio_queue = asyncio.Queue()

# Mimic sending a real-time stream by sending this many seconds of audio at a time.
# Used for file "streaming" only.
REALTIME_RESOLUTION = 0.250

subtitle_line_counter = 0

args = None

def subtitle_time_formatter(seconds, separator):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}"


def subtitle_formatter(response, format):
    global subtitle_line_counter
    subtitle_line_counter += 1

    start = response["start"]
    end = start + response["duration"]
    transcript = response.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")

    separator = "," if format == "srt" else '.'
    prefix = "- " if format == "vtt" else ""
    subtitle_string = (
        f"{subtitle_line_counter}\n"
        f"{subtitle_time_formatter(start, separator)} --> "
        f"{subtitle_time_formatter(end, separator)}\n"
        f"{prefix}{transcript}\n\n"
    )

    return subtitle_string


# Used for microphone streaming only.
def mic_callback(input_data, frame_count, time_info, status_flag):
    audio_queue.put_nowait(input_data)
    return (input_data, pyaudio.paContinue)


async def run(key, method, format, **kwargs):
    deepgram_url = f'{kwargs["host"]}/v1/listen?punctuate=true'

    if kwargs["model"]:
        deepgram_url += f"&model={kwargs['model']}"

    if kwargs["tier"]:
        deepgram_url += f"&tier={kwargs['tier']}"

    if method == "mic":
        deepgram_url += "&encoding=linear16&sample_rate=16000"

    elif method == "wav":
        data = kwargs["data"]
        deepgram_url += f'&channels={kwargs["channels"]}&sample_rate={kwargs["sample_rate"]}&encoding=linear16'

    # Connect to the real-time streaming endpoint, attaching our credentials.
    async with websockets.connect(
        deepgram_url, extra_headers={"Authorization": "Token {}".format(key)}
    ) as ws:
        print(f'ℹ️  Request ID: {ws.response_headers.get("dg-request-id")}')
        if kwargs["model"]:
            print(f'ℹ️  Model: {kwargs["model"]}')
        if kwargs["tier"]:
            print(f'ℹ️  Tier: {kwargs["tier"]}')
        print("🟢 (1/5) Successfully opened Deepgram streaming connection")

        async def sender(ws):
            print(
                f'🟢 (2/5) Ready to stream {method if (method == "mic" or method == "url") else kwargs["filepath"]} audio to Deepgram{". Speak into your microphone to transcribe." if method == "mic" else ""}'
            )

            if method == "mic":
                try:
                    while True:
                        mic_data = await audio_queue.get()
                        global all_mic_data
                        all_mic_data.append(mic_data)
                        print("Length of all_mic_data", len(all_mic_data))
                        await ws.send(mic_data)
                except websockets.exceptions.ConnectionClosedOK:
                    await ws.send(json.dumps({"type": "CloseStream"}))
                    print(
                        "🟢 (5/5) Successfully closed Deepgram connection, waiting for final transcripts if necessary"
                    )

                except Exception as e:
                    print(f"Error while sending: {str(e)}")
                    raise

            elif method == "url":
                # Listen for the connection to open and send streaming audio from the URL to Deepgram
                async with aiohttp.ClientSession() as session:
                    async with session.get(kwargs["url"]) as audio:
                        while True:
                            remote_url_data = await audio.content.readany()
                            await ws.send(remote_url_data)

                            # If no data is being sent from the live stream, then break out of the loop.
                            if not remote_url_data:
                                break

            elif method == "wav":
                nonlocal data
                # How many bytes are contained in one second of audio?
                byte_rate = (
                    kwargs["sample_width"] * kwargs["sample_rate"] * kwargs["channels"]
                )
                # How many bytes are in `REALTIME_RESOLUTION` seconds of audio?
                chunk_size = int(byte_rate * REALTIME_RESOLUTION)

                try:
                    while len(data):
                        chunk, data = data[:chunk_size], data[chunk_size:]
                        # Mimic real-time by waiting `REALTIME_RESOLUTION` seconds
                        # before the next packet.
                        await asyncio.sleep(REALTIME_RESOLUTION)
                        # Send the data
                        await ws.send(chunk)

                    await ws.send(json.dumps({"type": "CloseStream"}))
                    print(
                        "🟢 (5/5) Successfully closed Deepgram connection, waiting for final transcripts if necessary"
                    )
                except Exception as e:
                    print(f"🔴 ERROR: Something happened while sending, {e}")
                    raise e

            return

        async def receiver(ws):
            """Print out the messages received from the server."""
            first_message = True
            first_transcript = True
            transcript = ""

            async for msg in ws:
                res = json.loads(msg)
                if first_message:
                    print(
                        "🟢 (3/5) Successfully receiving Deepgram messages, waiting for finalized transcription..."
                    )
                    first_message = False
                try:
                    # handle local server messages
                    if res.get("msg"):
                        print(res["msg"])
                    if res.get("is_final"):
                        transcript = (
                            res.get("channel", {})
                            .get("alternatives", [{}])[0]
                            .get("transcript", "")
                        )
                        if kwargs["timestamps"]:
                            words = res.get("channel", {}).get("alternatives", [{}])[0].get("words", [])
                            start = words[0]["start"] if words else None
                            end = words[-1]["end"] if words else None
                            transcript += " [{} - {}]".format(start, end) if (start and end) else ""
                        if transcript != "":
                            if first_transcript:
                                print("🟢 (4/5) Began receiving transcription")
                                # if using webvtt, print out header
                                if format == "vtt":
                                    print("WEBVTT\n")
                                first_transcript = False
                            if format == "vtt" or format == "srt":
                                transcript = subtitle_formatter(res, format)
                            print(transcript)
                            keyboard.write(textToOutput(transcript), delay=0.01)
                            global all_transcripts
                            all_transcripts.append(transcript)

                        # if using the microphone, close stream if user says "goodbye"
                        if method == "mic" and "goodbye" in transcript.lower():
                            await ws.send(json.dumps({"type": "CloseStream"}))
                            print(
                                "🟢 (5/5) Successfully closed Deepgram connection, waiting for final transcripts if necessary"
                            )

                    # handle end of stream
                    if res.get("created"):
                        # save subtitle data if specified
                        if format == "vtt" or format == "srt":
                            data_dir = os.path.abspath(
                                os.path.join(os.path.curdir, "data")
                            )
                            if not os.path.exists(data_dir):
                                os.makedirs(data_dir)

                            transcript_file_path = os.path.abspath(
                                os.path.join(
                                    data_dir,
                                    f"{startTime.strftime('%Y%m%d%H%M')}.{format}",
                                )
                            )
                            with open(transcript_file_path, "w") as f:
                                f.write("".join(all_transcripts))
                            print(f"🟢 Subtitles saved to {transcript_file_path}")

                            # also save mic data if we were live streaming audio
                            # otherwise the wav file will already be saved to disk
                            if method == "mic":
                                wave_file_path = os.path.abspath(
                                    os.path.join(
                                        data_dir,
                                        f"{startTime.strftime('%Y%m%d%H%M')}.wav",
                                    )
                                )
                                wave_file = wave.open(wave_file_path, "wb")
                                wave_file.setnchannels(CHANNELS)
                                wave_file.setsampwidth(SAMPLE_SIZE)
                                wave_file.setframerate(RATE)
                                wave_file.writeframes(b"".join(all_mic_data))
                                wave_file.close()
                                print(f"🟢 Mic audio saved to {wave_file_path}")

                        print(
                            f'🟢 Request finished with a duration of {res["duration"]} seconds. Exiting!'
                        )
                except KeyError:
                    print(f"🔴 ERROR: Received unexpected API response! {msg}")

        # Set up microphone if streaming from mic
        async def microphone():
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                stream_callback=mic_callback,
            )

            stream.start_stream()

            global SAMPLE_SIZE
            SAMPLE_SIZE = audio.get_sample_size(FORMAT)

            while stream.is_active():
                await asyncio.sleep(0.1)

            stream.stop_stream()
            stream.close()

        functions = [
            asyncio.ensure_future(sender(ws)),
            asyncio.ensure_future(receiver(ws)),
        ]

        if method == "mic":
            functions.append(asyncio.ensure_future(microphone()))

        await asyncio.gather(*functions)


def validate_input(input):
    if input.lower().startswith("mic"):
        return input

    elif input.lower().endswith("wav"):
        if os.path.exists(input):
            return input

    elif input.lower().startswith("http"):
        return input

    raise argparse.ArgumentTypeError(
        f'{input} is an invalid input. Please enter the path to a WAV file, a valid stream URL, or "mic" to stream from your microphone.'
    )


def validate_format(format):
    if (
        format.lower() == ("text")
        or format.lower() == ("vtt")
        or format.lower() == ("srt")
    ):
        return format

    raise argparse.ArgumentTypeError(
        f'{format} is invalid. Please enter "text", "vtt", or "srt".'
    )

def validate_dg_host(dg_host):
    if (
        # Check that the host is a websocket URL
        dg_host.startswith("wss://")
        or dg_host.startswith("ws://")
    ):
        # Trim trailing slash if necessary
        if dg_host[-1] == '/':
            return dg_host[:-1]
        return dg_host 

    raise argparse.ArgumentTypeError(
            f'{dg_host} is invalid. Please provide a WebSocket URL in the format "{{wss|ws}}://hostname[:port]".'
    )

def parse_args():
    """Parses the command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Submits data to the real-time streaming endpoint."
    )
    parser.add_argument(
        "-k", "--key", help="YOUR_DEEPGRAM_API_KEY (authorization)"
    )
    parser.add_argument(
        "-p",
        "--provider",
        help="The provider to use for the audio. Can be 'Deepgram' or 'Assembly AI'. Defaults to 'deepgram'.",
        nargs="?",
        const=1,
        default="houndify"
    )
    parser.add_argument(
        "-i",
        "--input",
        help='Input to stream to Deepgram. Can be "mic" to stream from your microphone (requires pyaudio), the path to a WAV file, or the URL to a direct audio stream. Defaults to the included file preamble.wav',
        nargs="?",
        const=1,
        default="mic",
        type=validate_input,
    )
    parser.add_argument(
        "-m",
        "--model",
        help='Which model to make your request against. Defaults to none specified. See https://developers.deepgram.com/docs/models-overview for all model options.',
        nargs="?",
        const="",
        default="nova-general",
    )
    parser.add_argument(
        "-t",
        "--tier",
        help='Which model tier to make your request against. Defaults to none specified. See https://developers.deepgram.com/docs/tier for all tier options.',
        nargs="?",
        const="",
        default="",
    )
    parser.add_argument(
        "-ts",
        "--timestamps",
        help='Whether to include timestamps in the printed streaming transcript. Defaults to False.',
        nargs="?",
        const=1,
        default=False,
    )
    parser.add_argument(
        "-f",
        "--format",
        help='Format for output. Can be "text" to return plain text, "VTT", or "SRT". If set to VTT or SRT, the audio file and subtitle file will be saved to the data/ directory. Defaults to "text".',
        nargs="?",
        const=1,
        default="text",
        type=validate_format,
    )
    #Parse the host
    parser.add_argument(
        "--host",
        help='Point the test suite at a specific Deepgram URL (useful for on-prem deployments). Takes "{{wss|ws}}://hostname[:port]" as its value. Defaults to "wss://api.deepgram.com".',
        nargs="?",
        const=1,
        default="wss://api.deepgram.com",
        type=validate_dg_host,
    )
    return parser.parse_args()

texts = []
def textToOutput(text):
    # gpt_output = callGPT(text)
    # return gpt_output
    if len(texts) > 0:
        texts.append(text)
        return " " + text
    else:
        texts.append(text)
        return text

def main():
    """Entrypoint for the example."""
    # Parse the command-line arguments.
    global args
    args = parse_args()
    provider = args.provider
    print("The provider is", provider)
    if provider == "assembly":
        run_assembly()
        return

    if provider == "houndify":
        setup_houndify()
        return

    input = "mic"
    key = os.getenv("DEEPGRAM_API_KEY")
    format = args.format.lower()
    host = args.host

    try:
        if input.lower().startswith("mic"):
            asyncio.run(run(key, "mic", format, model=args.model, tier=args.tier, host=host, timestamps=args.timestamps))

        elif input.lower().endswith("wav"):
            if os.path.exists(input):
                # Open the audio file.
                with wave.open(input, "rb") as fh:
                    (
                        channels,
                        sample_width,
                        sample_rate,
                        num_samples,
                        _,
                        _,
                    ) = fh.getparams()
                    assert sample_width == 2, "WAV data must be 16-bit."
                    data = fh.readframes(num_samples)
                    asyncio.run(
                        run(
                            args.key,
                            "wav",
                            format,
                            model=args.model,
                            tier=args.tier,
                            data=data,
                            channels=channels,
                            sample_width=sample_width,
                            sample_rate=sample_rate,
                            filepath=args.input,
                            host=host,
                            timestamps=args.timestamps,
                        )
                    )
            else:
                raise argparse.ArgumentTypeError(
                    f"🔴 {args.input} is not a valid WAV file."
                )

        elif input.lower().startswith("http"):
            asyncio.run(run(args.key, "url", format, model=args.model, tier=args.tier, url=input, host=host, timestamps=args.timestamps))

        else:
            raise argparse.ArgumentTypeError(
                f'🔴 {input} is an invalid input. Please enter the path to a WAV file, a valid stream URL, or "mic" to stream from your microphone.'
            )

    except websockets.exceptions.InvalidStatusCode as e:
        print(f'🔴 ERROR: Could not connect to Deepgram! {e.headers.get("dg-error")}')
        print(
            f'🔴 Please contact Deepgram Support (developers@deepgram.com) with request ID {e.headers.get("dg-request-id")}'
        )
        return
    except websockets.exceptions.ConnectionClosedError as e:
        error_description = f"Unknown websocket error."
        print(
            f"🔴 ERROR: Deepgram connection unexpectedly closed with code {e.code} and payload {e.reason}"
        )

        if e.reason == "DATA-0000":
            error_description = "The payload cannot be decoded as audio. It is either not audio data or is a codec unsupported by Deepgram."
        elif e.reason == "NET-0000":
            error_description = "The service has not transmitted a Text frame to the client within the timeout window. This may indicate an issue internally in Deepgram's systems or could be due to Deepgram not receiving enough audio data to transcribe a frame."
        elif e.reason == "NET-0001":
            error_description = "The service has not received a Binary frame from the client within the timeout window. This may indicate an internal issue in Deepgram's systems, the client's systems, or the network connecting them."

        print(f"🔴 {error_description}")
        # TODO: update with link to streaming troubleshooting page once available
        # print(f'🔴 Refer to our troubleshooting suggestions: ')
        print(
            f"🔴 Please contact Deepgram Support (developers@deepgram.com) with the request ID listed above."
        )
        return

    except websockets.exceptions.ConnectionClosedOK:
        return

    except Exception as e:
        print(f"🔴 ERROR: Something went wrong! {e}")
        return


def run_deepgram():
    print("Running Deepgram")

def run_assembly():

    import assemblyai as aai
    aai.settings.api_key = os.getenv("ASSEMBLY_API_KEY")
    def on_open(session_opened: aai.RealtimeSessionOpened):
    # "This function is called when the connection has been established."
        print("Session ID:", session_opened.session_id)

    def on_data(transcript: aai.RealtimeTranscript):
    # "This function is called when a new transcript has been received."
        if not transcript.text:
            return

        if isinstance(transcript, aai.RealtimeFinalTranscript):
            print(transcript.text, end="\r\n")
            keyboard.write(textToOutput(transcript.text), delay=0.01)
        else:
            print(transcript.text, end="\r")

    def on_error(error: aai.RealtimeError):
    # "This function is called when the connection has been closed."
        print("An error occured:", error)

    def on_close():
    # "This function is called when the connection has been closed."
        print("Closing Session")

    transcriber = aai.RealtimeTranscriber(
    on_data=on_data,
    on_error=on_error,
    sample_rate=44_100,
    on_open=on_open, # optional
    on_close=on_close, # optional
    )

    # Start the connection
    transcriber.connect()

    # Open a microphone stream
    print("Opening microphone stream")
    microphone_stream = aai.extras.MicrophoneStream()

    # Press CTRL+C to abort
    transcriber.stream(microphone_stream)

    transcriber.close()
    
    print("Running Assembly AI")

# if __name__ == "__main__":
#     sys.exit(main() or 0)

audio = pyaudio.PyAudio()

# Start recording
stream = audio.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True,
                    frames_per_buffer=CHUNK)
class Transcript:
    def __init__(self):
        self.raw_transcript = ""
        self.transcript_on_editor = (0, "")
        
    # This will be called by the callback
    def getTranscriptOnEditor(self):
        return self.transcript_on_editor[1]

    def setTranscriptOnEditor(self, transcript, location):
        self.transcript_on_editor = (location, transcript)

    def getRawTranscript(self):
        return self.raw_transcript

    def setRawTranscript(self, transcript):
        self.raw_transcript = transcript

    def transcriptAfterCommands(self, transcript_from_server):
        transcript_from_server = self.transcript_on_editor[1] + transcript_from_server[self.transcript_on_editor[0]:]
        return transcript_from_server

    def isTranscriptProcessed(self, raw_transcript):
        return self.raw_transcript == raw_transcript
    
    def setRawTranscript(self, raw_transcript):
        self.raw_transcript = raw_transcript


def setup_houndify():
    client_id = os.getenv("HOUNDIFY_CLIENT_ID")
    client_key = os.getenv("HOUNDIFY_CLIENT_KEY")
    user_id = "test"
    houndify_client = houndify.StreamingHoundClient(client_id, client_key, userID=user_id, sampleRate=RATE, requestInfo={
        "PartialTranscriptsDesired": True,
        "ReturnResponseAudioAsURL": True,
        "UseFormattedTranscriptionAsDefault": True
    }, saveQuery=True)
    # houndify_client.start(MyListener())
    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )
    stream.start_stream()
    stoped = True
    try:
        # for _ in (1000):
        while True:
            if stoped:
                houndify_client.start(MyListener())
                stoped = False
            data = stream.read(CHUNK)
            global all_mic_data
            all_mic_data.append(data)
            # Check if there's some noise (data) before sending it to houndify_client
            if any(byte != b'\x00' for byte in data):
                # print("Filling the data")
                if houndify_client.fill(data):
                    print("Detecting Fill done")
                    stoped = True
                    houndify_client.finish()
            else:
                print("No data to send")
    except KeyboardInterrupt:
        stream.stop_stream()
        stream.close()
        audio.terminate()
    # houndify_client.finish()
    return houndify_client

loop = asyncio.new_event_loop()
# loop.run_forever()

def check_thread():
    current_thread = threading.current_thread()
    print(f"Current thread: {current_thread.name}")

check_thread()

class MyListener(houndify.HoundListener):
  def __init__(self):
    self.transcript = Transcript()
    self.identify_command_future = None  # Future for debouncing

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
  
  def onPartialTranscript(self, transcript_from_houndify):
    if (transcript_from_houndify == ""):
        return
    
    if self.transcript.isTranscriptProcessed(transcript_from_houndify):
        return
    
    check_thread()
    
    print(transcript_from_houndify)
    transcript_after_commands = self.transcript.transcriptAfterCommands(transcript_from_houndify)
    transcript_on_editor = self.transcript.getTranscriptOnEditor()
    # print("Transcript_from_houndify:", transcript_from_houndify)
    # print("Transcript_on_editor:", transcript_on_editor)
    # print("Transcript_after_commands:", transcript_after_commands)

    self.handle_identify_command_result(transcript_from_houndify, transcript_on_editor, transcript_after_commands)
    self.debounce_identify_command(transcript_from_houndify, transcript_on_editor, transcript_after_commands, self.handle_identify_command_result)
    return
  
  def onFinalResponse(self, response):
    print("Final response: " + str(response))

  def onError(self, err):
    print("Error " + str(err))


  def debounce_identify_command(self, transcript_from_houndify, transcript_on_editor ,transcript_after_commands, callback):
        # Cancel the previous task if it exists
        # print("The identify command task is", self.identify_command_future)
         
        if self.identify_command_future is not None and not self.identify_command_future.done():
            print("Cancelling the Future")
            self.identify_command_future.cancel()

        # Schedule a new task
        # print("The loop is", loop)
        self.identify_command_future = asyncio.run_coroutine_threadsafe(self.identify_command(transcript_from_houndify, transcript_on_editor, transcript_after_commands, callback), loop)
        return
  
  async def identify_command(self, transcript_from_houndify, transcript_on_editor, transcript_after_commands, handle_indentify_commad_result):
        # Function that actually calls the GPT model or any other logic
        # print("The identify command method is", transcript_after_commands)
        async def call_model(text):
            print("Calling the callGPT")
            result = callGPT(text)  # Your existing call to GPT or any other logic
            return result

        try:
            await asyncio.sleep(1)  # Debounce delay
            transcript_after_command_execution = await call_model(transcript_after_commands)
            loop.call_soon_threadsafe(handle_indentify_commad_result, transcript_from_houndify, transcript_on_editor, transcript_after_command_execution)  # Execute the callback in a thread-safe manner
        except asyncio.CancelledError:
            print ("The task was cancelled")
            pass  # Task was cancelled, do nothing

        return 
  
  def handle_identify_command_result(self, transcript_from_houndify, transcript_on_editor, transcript_after_command_execution):
        # print("In the handle_identify_command_result")
        # print("Identify command result:", transcript_after_command_execution)
        # print("The transcript from houndify is", transcript_from_houndify)
        # print("The transcript on editor is", transcript_on_editor)
        transcript_on_editor = self.transcript.getTranscriptOnEditor()
        raw_input = generate_raw_input(transcript_on_editor, transcript_after_command_execution)
        insert_at_cursor(raw_input)
        self.transcript.setTranscriptOnEditor(transcript_after_command_execution, len(transcript_from_houndify))
        self.transcript.setRawTranscript(transcript_from_houndify)
        global all_transcripts
        all_transcripts = [transcript_from_houndify]


def setup_hotkeys():
    print("Adding the hotkey")
    keyboard.add_hotkey('alt+o', main)
    keyboard.add_hotkey('ctrl+c', on_ctrl_c)

def keyboard_listener():
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        on_ctrl_c()

def on_ctrl_c(satisfaction=None):
    save_frames_and_transcription(all_mic_data, CHANNELS, 2, RATE, " ".join(all_transcripts), args.provider if args else  "houndify", satisfaction)
    sys.exit(1)
# keyboard.add_hotkey('ctrl+c', on_ctrl_c)

def generate_raw_input(oldResponse, newResponse):
    if (oldResponse == newResponse):
        return ""
    old = oldResponse
    new = newResponse
    output = ""
    if old == "":
        return new 
    # Find the common prefix length
    common_prefix_length = 0
    for i in range(min(len(old), len(new))):
        if old[i] == new[i]:
            common_prefix_length += 1
        else:
            break
    # Delete the non-common part of the old string
    output += "\b" * (len(old) - common_prefix_length)
    # Add the non-common part of the new string
    output += new[common_prefix_length:]
    
    return output

def insert_at_cursor(text):
    """
    Inserts text at the current cursor location. If the text contains a backspace character,
    it deletes the character before the cursor.
    
    Args:
    - text: The text to be inserted at the cursor location.
    """
    for char in text:
        if char == "\b":  # If the character is a backspace
            keyboard.press_and_release('backspace')
        elif char == "\n":  # If the character is a new line
            keyboard.press_and_release('enter')
        else:
            keyboard.write(char, delay=0.01)


def clear_and_refill_text(text):
    """
    Clears the current cursor location and refills it with the specified text.
    
    Args:
    - text: The text to refill at the cursor location.
    """
    keyboard.press_and_release('ctrl+a')
    keyboard.press_and_release('delete')
    keyboard.write(text, delay=0.01)


def on_alt_i():
    screenshot_base64 = take_screenshot()
    print("The screenshot is", screenshot_base64)
    prompt = "Describe what's happening in this screenshot."
    prompt = "rewrite my email to be more informal"
    vision_response = callVisionGPT(screenshot_base64, prompt)
    print("AI's response to the screenshot:", vision_response)
    clear_and_refill_text(vision_response)

keyboard.add_hotkey('alt+i', on_alt_i)



if __name__ == "__main__":
    try:
        setup_hotkeys()
        threading.Thread(target=keyboard_listener, daemon=True).start()
        loop.run_forever()
    except KeyboardInterrupt:
        # Clearing all input as per the updated instruction
        satisfaction = input("Are you satisfied with the audio quality? (y/n): ").strip()
        on_ctrl_c(satisfaction)
    finally:
        print("Exiting...")
        sys.exit(0)
