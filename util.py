import wave
import json

def save_frames_to_file(frames, channels, sample_width, frame_rate, filename):
    """
    Saves audio frames to a WAV file.

    Args:
    - frames: A list of audio frames.
    - channels: Number of audio channels.
    - sample_width: Sample width in bytes.
    - frame_rate: Frame rate in Hz.
    - filename: The name of the file to save the audio to.
    """
    try:
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(frame_rate)
            wf.writeframes(b''.join(frames))
    except Exception as e:
        print(f"Failed to save frames to file: {e}")

def save_frames_and_transcription(frames, channels, sample_width, frame_rate, transcription, provider):
    print("The transcription is", transcription)
    """
    Saves audio frames to a WAV file and transcription to a JSON file with camelCase naming convention.
    The file name is derived from the transcription.

    Args:
    - frames: A list of audio frames.
    - channels: Number of audio channels.
    - sample_width: Sample width in bytes.
    - frame_rate: Frame rate in Hz.
    - transcription: The transcription text of the audio.
    """
    try:
        # Convert transcription to camelCase for the filename
        from datetime import datetime
        current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M_")
        filename_base = 'logs/' + current_datetime + ''.join(x for x in transcription.title() if not x.isspace())
        if len(filename_base) > 250:
            filename_base = filename_base[:248] + "..."
        
        # Save the frames to a WAV file
        save_frames_to_file(frames, channels, sample_width, frame_rate, filename_base + ".wav")

        # Create a dictionary with the audio file details
        audio_details = {
            "channels": channels,
            "sampleWidth": sample_width,
            "frameRate": frame_rate,
            "provider": provider,
            "transcript": transcription if len(transcription) <= 250 else transcription[:248] + "..."
        }

        # Save the dictionary to a JSON file with the same name as the audio file
        json_filename = filename_base + ".json"
        with open(json_filename, 'w') as json_file:
            json.dump(audio_details, json_file)
    except Exception as e:
        print(f"Failed to save frames and transcription: {e}")

import pyautogui
import datetime
import os

def take_screenshot():
    """
    Takes a screenshot of the entire screen, saves it in the screenshot directory with a timestamp, and returns the base64 encoded string of the screenshot.
    """
    import base64
    from io import BytesIO

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    screenshot_directory = "screenshot"
    os.makedirs(screenshot_directory, exist_ok=True)
    screenshot_filename = f"{screenshot_directory}/screenshot_{timestamp}.png"
    screenshot = pyautogui.screenshot()
    screenshot.save(screenshot_filename)
    print(f"Screenshot saved in {screenshot_directory} as {screenshot_filename}")

    buffer = BytesIO()
    screenshot.save(buffer, format="PNG")
    base64_image = base64.b64encode(buffer.getvalue()).decode()

    return base64_image
