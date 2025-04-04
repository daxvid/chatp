import pjsua2 as pj
import whisper
import edge_tts
import asyncio
import os
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from pathlib import Path

class Config:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
    @property
    def sip_config(self):
        return self.config['sip']
    
    @property
    def call_config(self):
        return self.config['call']
    
    @property
    def responses(self):
        return self.config['responses']

def load_whisper_model():
    # Create models directory if it doesn't exist
    model_dir = Path("models/whisper")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    # Set model path
    model_path = model_dir / "small.pt"
    
    # Load model from local path if exists, otherwise download
    try:
        model = whisper.load_model("small", download_root=str(model_dir))
        print(f"Loaded whisper model from {model_path}")
    except Exception as e:
        print(f"Error loading model from {model_path}: {e}")
        print("Downloading model...")
        model = whisper.load_model("small", download_root=str(model_dir))
        print("Model downloaded successfully")
    
    return model

class CallHandler(pj.Call):
    def __init__(self, acc, call_id, config):
        pj.Call.__init__(self, acc, call_id)
        self.recorder = None
        self.player = None
        self.whisper_model = load_whisper_model()
        self.vectorizer = TfidfVectorizer()
        self.config = config
        self.responses = config.responses
        
    def onCallState(self, prm):
        if self.getInfo().state == pj.PJSIP_INV_STATE_DISCONNECTED:
            print("Call disconnected")
            if self.recorder:
                self.recorder.delete()
            if self.player:
                self.player.delete()
        elif self.getInfo().state == pj.PJSIP_INV_STATE_CONFIRMED:
            print("Call connected")
            self.startCall()

    def startCall(self):
        # Play initial message
        self.playAudio(self.config.call_config['initial_message'])
        
        # Start recording user's response
        self.startRecording()
        
        # Wait for user's response
        asyncio.run(self.processUserResponse())

    async def processUserResponse(self):
        # Wait for recording to complete
        await asyncio.sleep(self.config.call_config['response_timeout'])
        
        # Stop recording
        self.stopRecording()
        
        # Transcribe user's response
        transcription = self.transcribeAudio("user_response.wav")
        
        # Analyze response and get appropriate reply
        response = self.analyzeResponse(transcription)
        
        # Convert response to speech
        await self.textToSpeech(response)
        
        # Play the response
        self.playAudio("response.wav")

    def playAudio(self, filename):
        self.player = pj.AudioMediaPlayer()
        self.player.createPlayer(filename)
        self.player.startTransmit(self.getAudioVideoMedia()[0])

    def startRecording(self):
        self.recorder = pj.AudioMediaRecorder()
        self.recorder.createRecorder("user_response.wav")
        self.getAudioVideoMedia()[0].startTransmit(self.recorder)

    def stopRecording(self):
        if self.recorder:
            self.recorder.stopTransmit(self.getAudioVideoMedia()[0])

    def transcribeAudio(self, filename):
        result = self.whisper_model.transcribe(filename)
        return result["text"]

    def analyzeResponse(self, text):
        # Convert responses to vectors
        response_texts = list(self.responses.values())
        response_vectors = self.vectorizer.fit_transform(response_texts)
        
        # Convert input text to vector
        input_vector = self.vectorizer.transform([text])
        
        # Calculate similarity scores
        similarities = cosine_similarity(input_vector, response_vectors)[0]
        
        # Get the most similar response
        most_similar_idx = np.argmax(similarities)
        return response_texts[most_similar_idx]

    async def textToSpeech(self, text):
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save("response.wav")

class Account(pj.Account):
    def __init__(self, config):
        pj.Account.__init__(self)
        self.config = config

    def onIncomingCall(self, prm):
        call = CallHandler(self, prm.callId, self.config)
        call.answer(prm.code)

def main():
    # Load configuration
    config = Config()
    
    # Initialize PJSIP
    ep = pj.Endpoint()
    ep.libCreate()
    
    # Configure endpoint
    ep_cfg = pj.EpConfig()
    ep_cfg.uaConfig.maxCalls = 4
    ep_cfg.uaConfig.userAgent = "Python Auto Caller"
    ep_cfg.uaConfig.stunServer = []
    ep_cfg.uaConfig.nameserver = []
    ep.libInit(ep_cfg)
    
    # Create SIP transport
    sipTpConfig = pj.TransportConfig()
    sipTpConfig.port = config.sip_config['port']
    ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, sipTpConfig)
    
    # Start the library
    ep.libStart()
    
    # Create account
    acc_cfg = pj.AccountConfig()
    acc_cfg.idUri = f"sip:{config.sip_config['account']}"
    acc_cfg.regConfig.registrarUri = f"sip:{config.sip_config['server']}"
    acc_cfg.regConfig.registerOnAdd = True
    acc_cfg.regConfig.timeoutSec = config.sip_config['register_refresh']
    acc_cfg.regConfig.retryIntervalSec = 60
    acc_cfg.regConfig.firstRetryIntervalSec = 20
    acc_cfg.regConfig.delayBeforeRefreshSec = 5
    acc_cfg.regConfig.dropCallsOnFail = False
    acc_cfg.regConfig.unregWaitMsec = 5000
    acc_cfg.regConfig.proxyUse = pj.PJSIP_REGISTER_INIT_PROXY
    acc_cfg.sipConfig.authCreds.append(
        pj.AuthCredInfo("digest", "*", config.sip_config['username'], 0, config.sip_config['password'])
    )
    
    acc = Account(config)
    acc.create(acc_cfg)
    
    # Make outbound call
    call = CallHandler(acc, -1, config)
    call_prm = pj.CallOpParam()
    call.makeCall(config.call_config['target_number'], call_prm)
    
    # Keep the program running
    try:
        while True:
            ep.libHandleEvents(10)
    except KeyboardInterrupt:
        print("Shutting down...")
        ep.libDestroy()
        ep.libDelete()

if __name__ == "__main__":
    main() 