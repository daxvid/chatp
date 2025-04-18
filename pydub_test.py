import pydub
from datetime import datetime

from fix_wav_in_place import fix_wav_file_in_place

min_silence_len = 700
silence_thresh = -60
start_time = datetime.now()
file = "recordings/13382344636_20250418_151033_tmp.wav"
fix_wav_file_in_place(file)
audio = pydub.AudioSegment.from_wav(file)
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
