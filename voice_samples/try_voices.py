"""Make a short Hinglish sample for each candidate voice -> voice_samples/<name>.wav"""
import asyncio, sys, wave
import aiohttp
from dotenv import load_dotenv
from livekit.agents import inference, utils

load_dotenv(".env")
VOICES = {
    "indian_lady": "3b554273-4299-48b9-9aaf-eefd438e3941",
    "indian_support_lady": "ff1bb1a9-c582-4570-9670-5f46169d0fc8",
    "hinglish_lady": "95d51f79-c397-46f9-b49a-23763d3eaa2d",
    "hindi_narrator_woman": "c1abd502-9231-4558-a054-10ac950c356d",
}
TEXT = "Namaste, main Asha bol rahi hoon Happy Paws se. Bruno ka kal subah gyaarah baje appointment hai. Kya aap aa paayenge?"

async def main():
    async with aiohttp.ClientSession() as http:
        for name, vid in VOICES.items():
            try:
                tts = inference.TTS(model="cartesia/sonic-3", voice=vid, language="hi", http_session=http)
                frames = []
                async for ev in tts.synthesize(TEXT):
                    frames.append(ev.frame)
                if not frames:
                    print(name, "NO AUDIO"); continue
                f0 = frames[0]
                with wave.open(f"voice_samples/{name}.wav", "wb") as w:
                    w.setnchannels(f0.num_channels); w.setsampwidth(2); w.setframerate(f0.sample_rate)
                    for fr in frames: w.writeframes(bytes(fr.data))
                print(name, "OK", round(sum(fr.samples_per_channel for fr in frames)/f0.sample_rate,1), "sec")
            except Exception as e:
                print(name, "FAILED", type(e).__name__, str(e)[:200])

asyncio.run(main())
