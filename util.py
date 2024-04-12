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
        filename_base = 'logs/'+ ''.join(x for x in transcription.title() if not x.isspace())
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

