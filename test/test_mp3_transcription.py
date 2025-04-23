import os
import sys
import time
import json
from pathlib import Path
import logging
from datetime import datetime

# Add parent directory to path so we can import whisper_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from whisper_manager import WhisperManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("audio_transcription_test")

def transcribe_directory(input_dir, output_file=None, file_types=None):
    """
    Transcribe all audio files in the specified directory
    
    Args:
        input_dir: Directory containing audio files
        output_file: JSON file to save results (optional)
        file_types: List of file extensions to process (default: ['.mp3', '.wav'])
    """
    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        logger.error(f"Directory not found or not a directory: {input_dir}")
        return
    
    # Default file types if not specified
    if file_types is None:
        file_types = ['.mp3', '.wav']
    
    # Initialize Whisper with turbo model
    whisper_manager = WhisperManager(model_size="turbo", model_dir="../models/whisper")
    
    # Find all audio files with specified extensions
    audio_files = []
    for file_type in file_types:
        audio_files.extend(list(input_path.glob(f"**/*{file_type}")))
    
    logger.info(f"Found {len(audio_files)} audio files in {input_dir}")
    
    results = []
    results602 = []
    total_duration = 0
    successful_count = 0
    
    for audio_file in audio_files:
        logger.info(f"Processing: {audio_file}")
        
        # Record start time
        start_time = time.time()
        
        # Transcribe the file
        transcription = whisper_manager.transcribe(str(audio_file))
        
        # Calculate duration
        duration = time.time() - start_time
        total_duration += duration
        
        if transcription is not None:
            successful_count += 1
        
        # Store results
        file_result = {
            "file": str(audio_file),
            "file_type": audio_file.suffix,
            "duration_seconds": round(duration, 2),
            "success": transcription is not None,
        }
        
        if transcription:
            file_result["text"] = transcription["text"]
            # Only include segments if they exist and contain useful information
            if "segments" in transcription and transcription["segments"]:
                # Store segments but limit to important fields to reduce JSON size
                file_result["segments"] = [
                    {
                        "id": seg.get("id"),
                        "start": seg.get("start"),
                        "end": seg.get("end"),
                        "text": seg.get("text"),
                        "no_speech_prob": seg.get("no_speech_prob"),
                        "avg_logprob": seg.get("avg_logprob"),
                        "compression_ratio": seg.get("compression_ratio")
                        # "temperature": seg.get("temperature")
                    }
                    for seg in transcription["segments"]
                ]
            if "602" in transcription["text"] or "603" in transcription["text"]:
                results602.append(file_result)
        else:
            file_result["text"] = None
            file_result["error"] = "Transcription failed"
        
        results.append(file_result)
        
        logger.info(f"Completed in {duration:.2f} seconds: {audio_file}")
    
    # Calculate summary statistics
    summary = {
        "total_files": len(audio_files),
        "successful_transcriptions": successful_count,
        "failed_transcriptions": len(audio_files) - successful_count,
        "total_duration_seconds": round(total_duration, 2),
        "average_duration_seconds": round(total_duration / max(1, len(audio_files)), 2),
        "timestamp": datetime.now().isoformat(),
        "file_types": file_types
    }
    
    # Print summary to console
    logger.info(f"\nTranscription Summary:")
    logger.info(f"  Total files: {summary['total_files']}")
    logger.info(f"  Successful: {summary['successful_transcriptions']}")
    logger.info(f"  Failed: {summary['failed_transcriptions']}")
    logger.info(f"  Total time: {summary['total_duration_seconds']:.2f} seconds")
    logger.info(f"  Average time per file: {summary['average_duration_seconds']:.2f} seconds")
    
    # Save results if output file specified
    if output_file:
        output_path = Path(output_file)
        if not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "summary": summary,
                "results": results
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Results saved to {output_file}")
        
        # Also save a simplified summary file without full transcriptions
        summary_path = output_path.with_name(f"{output_path.stem}_summary{output_path.suffix}")
        with open(summary_path, 'w', encoding='utf-8') as f:
            # Create a simplified version of results without full transcription text
            simplified_results = [
                {
                    "file": r["file"],
                    "file_type": r["file_type"],
                    "duration_seconds": r["duration_seconds"],
                    "success": r["success"],
                    "text_length": len(r.get("text", "")) if r.get("text") else 0
                }
                for r in results
            ]
            
            json.dump({
                "summary": summary,
                "results": simplified_results
            }, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Summary saved to {summary_path}")
    
    # Clean up
    whisper_manager.shutdown()

    # Save results603 to a file
    results602_path = Path("results602.json")
    with open(results602_path, 'w', encoding='utf-8') as f:
        json.dump(results602, f, ensure_ascii=False, indent=2)
    logger.info(f"Results saved to {results602_path}")
    
    return results

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Transcribe audio files in a directory")
    parser.add_argument("input_dir", help="Directory containing audio files")
    parser.add_argument("--output", "-o", help="Output JSON file to save results")
    parser.add_argument("--file-types", "-t", nargs="+", default=['.mp3', '.wav'], 
                        help="File extensions to process (default: .mp3 .wav)")
    
    args = parser.parse_args()
    
    output_file = args.output
    if not output_file:
        # Default output filename based on timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"transcription_results_{timestamp}.json"
    
    # Run transcription
    transcribe_directory(args.input_dir, output_file, args.file_types) 