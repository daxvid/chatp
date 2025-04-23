# Audio Transcription Test

This script allows you to batch transcribe all audio files (MP3 or WAV) in a specified directory using Whisper's Turbo model.

## Features

- Transcribes all MP3 and WAV files in a directory (including subdirectories)
- Records transcription time for each file
- Outputs results to a JSON file
- Uses Whisper's "turbo" model by default
- Supports GPU acceleration if available

## Usage

```bash
python test_mp3_transcription.py /path/to/audio/directory [options]
```

### Options

- `--output`, `-o`: Specify output JSON file path (default: transcription_results_TIMESTAMP.json)
- `--file-types`, `-t`: Specify file extensions to process (default: .mp3 .wav)

### Examples

Transcribe all MP3 and WAV files in the recordings directory:
```bash
python test_mp3_transcription.py ../recordings
```

Transcribe only MP3 files:
```bash
python test_mp3_transcription.py ../recordings --file-types .mp3
```

Specify custom output file:
```bash
python test_mp3_transcription.py ../recordings --output my_results.json
```

## Output Format

The script generates a JSON file with the following structure:

```json
{
  "timestamp": "2023-04-25T15:30:45.123456",
  "total_files": 5,
  "file_types": [".mp3", ".wav"],
  "results": [
    {
      "file": "/path/to/file1.mp3",
      "file_type": ".mp3",
      "duration_seconds": 12.34,
      "success": true,
      "text": "Transcribed text content...",
      "segments": [...]
    },
    {
      "file": "/path/to/file2.wav",
      "file_type": ".wav",
      "duration_seconds": 7.89,
      "success": true,
      "text": "Another transcription...",
      "segments": [...]
    }
  ]
}
```

## Requirements

- Python 3.6+
- Whisper AI library
- torch (with CUDA support for GPU acceleration)

Make sure the `whisper_manager.py` file is in the parent directory or properly installed. 