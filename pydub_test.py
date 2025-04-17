from pydub import AudioSegment
from pydub.silence import split_on_silence
from datetime import datetime

start_time = datetime.now()
audio = AudioSegment.from_wav("recordings/input.wav")
chunks = split_on_silence(audio, 
    min_silence_len=800,
    silence_thresh=-50,
    keep_silence=800
)

for i, chunk in enumerate(chunks):
    chunk.export(f"recordings/output_{i:03d}.wav", format="wav")

end_time =  datetime.now()
print(f"Total chunks: {len(chunks)}")
print(f"Time taken: {end_time - start_time}")
