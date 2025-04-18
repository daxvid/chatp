import pydub
from datetime import datetime

min_silence_len = 700
silence_thresh = -60
start_time = datetime.now()
audio = pydub.AudioSegment.from_wav("recordings/input.wav")
chunks = pydub.silence.split_on_silence(audio, 
    min_silence_len=min_silence_len,
    silence_thresh=silence_thresh,
    keep_silence=min_silence_len
)

for i, chunk in enumerate(chunks):
    chunk.export(f"recordings/output_{i:03d}.wav", format="wav")

end_time =  datetime.now()
print(f"Total chunks: {len(chunks)}")
print(f"Time taken: {end_time - start_time}")
