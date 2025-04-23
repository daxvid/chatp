#!/usr/bin/env python3
"""
Example script showing how to use the audio transcription test
"""
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the test directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the transcription function
from test_mp3_transcription import transcribe_directory

# Define the recordings directory (relative to the project root)
RECORDINGS_DIR = Path(__file__).parent.parent / "recordings"

# Define output file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_FILE = Path(__file__).parent / f"transcription_results_{timestamp}.json"

def main():
    """Run transcription on the recordings directory"""
    print(f"Starting transcription of audio files in: {RECORDINGS_DIR}")
    print(f"Results will be saved to: {OUTPUT_FILE}")
    
    # Run transcription with default settings (MP3 and WAV files)
    results = transcribe_directory(
        input_dir=RECORDINGS_DIR,
        output_file=OUTPUT_FILE
    )
    
    # Print summary
    if results:
        print("\nTranscription Summary:")
        print(f"Total files processed: {len(results)}")
        
        successful = sum(1 for r in results if r['success'])
        print(f"Successfully transcribed: {successful}")
        print(f"Failed: {len(results) - successful}")
        
        if successful > 0:
            avg_time = sum(r['duration_seconds'] for r in results if r['success']) / successful
            print(f"Average transcription time: {avg_time:.2f} seconds")
    else:
        print("No results returned. Check if any audio files were found.")

if __name__ == "__main__":
    main() 