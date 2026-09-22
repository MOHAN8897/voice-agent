import asyncio
import os
import edge_tts

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'public', 'audio', 'voxly')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Using Microsoft's studio-grade AnaNeural (cheerful, friendly, high-clarity voice for Voxly robot)
VOICE = "en-US-AnaNeural"

CLIPS = [
    ("hero_step1.mp3", "Hello! Hiii! I'm Voxly! Nice to meet you!"),
    ("hero_step2.mp3", "Hiii! Excited to scale your voice workflows! Ready for 500 plus calls."),
    ("hero_step3.mp3", "Whoaaa! Watch this barrel roll! 360 degree celebratory spin and wave!"),
    ("hero_step4.mp3", "Don't tickle me! Haha! Double high five to you!"),
    ("hero_step5.mp3", "Double barrel roll and high five! Let's conquer customer calls!"),
    ("hero_pouty.mp3", "Hey! Don't poke me, I have calls to make! Click live mic chat instead!"),
    ("hero_wave.mp3", "Hiii! Waving back at you! Always ready for the next customer call."),
    ("hero_roll.mp3", "Whoaaa! Full 360 celebratory barrel roll spin! Agility at scale."),
    ("hero_think.mp3", "Analyzing your knowledge base... I can resolve 85 percent of tier-one questions instantly!"),
    ("hero_celebrate.mp3", "Woohoo! Another qualified lead booked straight into your calendar!"),
    ("hero_dance.mp3", "Look at these moves! Grooving through phone queues with zero hold times!"),
    ("hero_double_wave.mp3", "Double high-five! Ready to handle 500 simultaneous calls!"),
    ("hero_surprise.mp3", "Did you know? Sub-400 millisecond response time means natural, human conversation!")
]

async def generate_all():
    print(f"Generating {len(CLIPS)} neural TTS clips into {OUTPUT_DIR}...")
    for filename, text in CLIPS:
        target_path = os.path.join(OUTPUT_DIR, filename)
        # Childish, high-energy, fast and cheerful voice (+20% rate for fast cadence, +5Hz pitch for cute child tone)
        communicate = edge_tts.Communicate(text, VOICE, pitch="+5Hz", rate="+20%")
        await communicate.save(target_path)
        size = os.path.getsize(target_path)
        print(f"[OK] Generated {filename} ({size} bytes): \"{text}\"")

if __name__ == "__main__":
    asyncio.run(generate_all())
