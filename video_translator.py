# VIDEO TRANSLATION SERVICE
import subprocess
import os
import math
import google.generativeai as genai
from moviepy import VideoFileClip, AudioFileClip
import whisper
from deep_translator import GoogleTranslator
from elevenlabs import ElevenLabs

# API Keys (You should move these to environment variables for security)
ELEVENLABS_API_KEY = "sk_63705dc591df5199bf5317796c11a14601ae307c85ec5e8e"
GEMINI_API_KEY = "AIzaSyDn6vnBLrnPal9bXxW9TC-Z29d4yGqqaa4"

# Language mapping
LANGUAGE_CODES = {
    'hindi': 'hi',
    'bengali': 'bn',
    'telugu': 'te',
    'marathi': 'mr',
    'tamil': 'ta',
    'gujarati': 'gu',
    'kannada': 'kn',
    'malayalam': 'ml',
    'punjabi': 'pa',
    'odia': 'or',
    'urdu': 'ur',
    'assamese': 'as',
    'english': 'en'
}

def get_video_duration(video_path):
    """Get the duration of the video in seconds"""
    video = VideoFileClip(video_path)
    duration = video.duration
    video.close()
    return duration

def extract_audio_from_video(video_path, output_dir):
    """Extract audio from MP4 video file"""
    print("🎬 Extracting audio from video...")
    video = VideoFileClip(video_path)
    audio_path = os.path.join(output_dir, "extracted_audio.mp3")
    # MoviePy 2.x removed verbose and logger parameters
    video.audio.write_audiofile(audio_path)
    video.close()
    print("✅ Audio extracted successfully!")
    return audio_path

def slow_down_audio_for_transcription(audio_path, language, output_dir):
    """Slow down audio if language is not English to help transcription"""
    if language == 'en':
        print("✅ Audio is in English, no speed adjustment needed for transcription")
        return audio_path

    print(f"🔍 Non-English audio detected ({language}), slowing down for better transcription...")
    slowed_audio_path = os.path.join(output_dir, "slowed_audio_for_transcription.mp3")

    cmd = [
        'ffmpeg',
        '-i', audio_path,
        '-filter:a', 'atempo=0.8',
        '-y',
        slowed_audio_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ Audio slowed down successfully for transcription!")
        return slowed_audio_path
    except subprocess.CalledProcessError as e:
        print(f"❌ Audio slowing failed: {e}")
        return audio_path

def adjust_video_speed(video_path, original_duration, target_duration, output_path):
    """Adjust video speed to match target duration"""
    print(f"⚡ Adjusting video speed: {original_duration:.2f}s → {target_duration:.2f}s")

    speed_factor = target_duration / original_duration
    speed_factor = max(0.5, min(2.0, speed_factor))

    if abs(speed_factor - 1.0) < 0.05:
        print("📊 Speed adjustment negligible, using original video")
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    print(f"🎚 Applying video speed factor: {speed_factor:.2f}x")

    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-filter:v', f'setpts={1/speed_factor}*PTS',
        '-y',
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ Video speed adjusted successfully!")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"❌ Video speed adjustment failed: {e}")
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

def merge_audio_with_video(adjusted_video_path, new_audio_path, output_path):
    """Merge new audio with adjusted video using FFmpeg"""
    print("🎬 Merging new audio with adjusted video...")

    cmd = [
        'ffmpeg',
        '-i', adjusted_video_path,
        '-i', new_audio_path,
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-shortest',
        '-y',
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ Video with translated audio created successfully!")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg merge failed: {e}")
        print("🔄 Falling back to MoviePy...")

        video = VideoFileClip(adjusted_video_path)
        new_audio = AudioFileClip(new_audio_path)

        if new_audio.duration > video.duration:
            new_audio = new_audio.subclip(0, video.duration)

        final_video = video.set_audio(new_audio)
        # MoviePy 2.x removed verbose and logger parameters
        final_video.write_videofile(output_path, codec='libx264')

        video.close()
        new_audio.close()
        final_video.close()

        print("✅ Video with translated audio created (MoviePy fallback)!")
        return output_path

def detect_audio_language_and_transcribe(audio_path, output_dir):
    """Detect language and transcribe audio"""
    print("🔍 Detecting language...")
    model = whisper.load_model("small")

    audio = whisper.load_audio(audio_path)
    audio = whisper.pad_or_trim(audio)

    mel = whisper.log_mel_spectrogram(audio).to(model.device)

    _, probs = model.detect_language(mel)
    detected_language = max(probs, key=probs.get)
    print(f"🎯 Detected Language: {detected_language} (confidence: {probs[detected_language]:.2f})")

    processed_audio_path = slow_down_audio_for_transcription(audio_path, detected_language, output_dir)

    print("📝 Transcribing audio...")
    if processed_audio_path != audio_path:
        result = model.transcribe(processed_audio_path)
        if os.path.exists(processed_audio_path) and processed_audio_path != audio_path:
            os.remove(processed_audio_path)
    else:
        result = model.transcribe(audio_path)

    print("Original Text:", result["text"])
    return result["text"], detected_language

def optimize_text_for_timing(text, target_lang, gemini_api_key, original_duration):
    """Use Gemini to optimize text length to fit the original video duration"""
    print("🧠 Using Gemini to optimize text for perfect timing...")

    try:
        # Configure Gemini API
        genai.configure(api_key=gemini_api_key)

        lang_names = {
            'hi': 'Hindi', 'mr': 'Marathi', 'ta': 'Tamil', 'te': 'Telugu',
            'bn': 'Bengali', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'it': 'Italian', 'en': 'English', 'pa': 'Punjabi', 'gu': 'Gujarati',
            'kn': 'Kannada', 'ml': 'Malayalam', 'or': 'Odia', 'ur': 'Urdu',
            'as': 'Assamese'
        }

        lang_name = lang_names.get(target_lang, 'the target language')

        words_per_second = {
            'hi': 2.5, 'mr': 2.5, 'ta': 2.8, 'te': 2.8, 'bn': 2.6,
            'es': 3.0, 'fr': 3.0, 'de': 3.0, 'it': 3.0, 'en': 3.0,
            'pa': 2.5, 'gu': 2.5, 'kn': 2.8, 'ml': 2.8, 'or': 2.6,
            'ur': 2.5, 'as': 2.6
        }

        target_wps = words_per_second.get(target_lang, 2.8)
        target_word_count = int(original_duration * target_wps)

        prompt = f"""
        You are an experienced teacher explaining concepts to students. Rewrite the following text in clear, educational {lang_name}.

        CRITICAL TIMING CONSTRAINT:
        - The final spoken version MUST fit within {original_duration:.1f} seconds
        - Target word count: approximately {target_word_count} words
        - Speak at a natural teaching pace (about {target_wps} words per second)

        TEACHING GUIDELINES:
        - Explain concepts clearly like a teacher to students
        - Convert the normal english terms back to english
        - Use proper educational language but keep it accessible
        - Maintain academic accuracy while being engaging
        - Structure the explanation logically
        - Adjust the length to fit the time constraint perfectly
        - Keep the core meaning exactly the same
        - Make sure that the text you provide is completely in the given language even words in english should be transliterated in hindi text and does not have any english text even in brackets.

        LENGTH ADJUSTMENT STRATEGY:
        If the text is too long: Remove redundant parts, use more concise language
        If the text is too short: Add brief explanations, examples, or context
        Aim for natural pacing that fits {original_duration:.1f} seconds exactly

        TEXT TO OPTIMIZE: "{text}"

        Return only the timing-optimized educational version without any additional explanations.
        The spoken version of your response must naturally take {original_duration:.1f} seconds to deliver.
        """

        # Try different Gemini models
        model = None
        try:
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content(prompt)
        except:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(prompt)
            except:
                model = genai.GenerativeModel('gemini-1.5-pro')
                response = model.generate_content(prompt)

        optimized_text = response.text.strip()

        if optimized_text.startswith('"') and optimized_text.endswith('"'):
            optimized_text = optimized_text[1:-1]

        remove_phrases = [
            "Here's the timing-optimized version:",
            "As a teacher would explain within the time limit:",
            "Educational version optimized for timing:",
            "Here's the teacher's explanation fitting the duration:",
            "Sure, here's the timing-optimized educational rewrite:",
            "Of course! Here's the version that fits the time constraint:"
        ]

        for phrase in remove_phrases:
            if optimized_text.startswith(phrase):
                optimized_text = optimized_text[len(phrase):].strip()

        actual_word_count = len(optimized_text.split())
        print(f"✅ Teacher-Optimized Text ({actual_word_count} words): {optimized_text}")
        print(f"⏱ Target: {target_word_count} words for {original_duration:.1f}s duration")
        return optimized_text

    except Exception as e:
        print(f"❌ Gemini optimization failed: {e}")
        print("🔄 Using direct translation instead...")
        return GoogleTranslator(source='auto', target=target_lang).translate(text)

def translate_with_timing_optimization(text, target_lang, gemini_api_key, original_duration):
    """Translate text with Gemini educational optimization and timing constraint"""
    print("🌍 Translating with timing optimization...")

    try:
        print(f"Translating from detected language to {target_lang}...")
        translated = GoogleTranslator(source='auto', target=target_lang).translate(text)
        print(f"Initial Translation: {translated}")

        if len(translated.split()) > 3:
            optimized = optimize_text_for_timing(translated, target_lang, gemini_api_key, original_duration)
            return optimized
        else:
            print("📝 Text too short for optimization, using direct translation")
            return translated

    except Exception as e:
        print(f"❌ Enhanced translation failed: {e}")
        return GoogleTranslator(source='auto', target=target_lang).translate(text)

def text_to_speech(text, api_key, output_filename):
    """Convert text to speech using ElevenLabs"""
    print("🔊 Converting text to speech...")
    client = ElevenLabs(api_key=api_key)

    audio = client.text_to_speech.convert(
        voice_id="3gsg3cxXyFLcGIfNbM6C",  # Josh voice
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        voice_settings={
            "stability": 0.6,
            "similarity_boost": 0.9,
            "style": 0.6,
            "use_speaker_boost": True
        }
    )

    audio_data = b"".join(audio)

    with open(output_filename, "wb") as f:
        f.write(audio_data)

    print("✅ Audio generated successfully!")
    return output_filename

def video_translation_pipeline(video_path, target_language, output_dir):
    """Complete pipeline: Video → Extract Audio → Detect → Translate → Voice → Merge"""
    
    print(f"🚀 Starting video translation pipeline for language: {target_language}")
    
    # Map frontend language to language code
    target_lang_code = LANGUAGE_CODES.get(target_language.lower(), 'hi')
    print(f"📝 Target language code: {target_lang_code}")
    
    # Get original video duration
    original_duration = get_video_duration(video_path)
    print(f"⏱ Original video duration: {original_duration:.2f} seconds")

    # Step 1: Extract audio from video
    extracted_audio_path = extract_audio_from_video(video_path, output_dir)

    # Step 2: Detect language and transcribe
    original_text, detected_lang = detect_audio_language_and_transcribe(extracted_audio_path, output_dir)

    # Step 3: Translate text with Gemini optimization
    translated_text = translate_with_timing_optimization(
        original_text, 
        target_lang_code, 
        GEMINI_API_KEY, 
        original_duration
    )

    # Step 4: Convert to speech
    new_audio_path = os.path.join(output_dir, "translated_audio.mp3")
    text_to_speech(translated_text, ELEVENLABS_API_KEY, new_audio_path)

    # Step 5: Get new audio duration and adjust VIDEO speed to match it
    new_audio_duration = AudioFileClip(new_audio_path).duration
    AudioFileClip(new_audio_path).close()

    print(f"⏱ Generated audio duration: {new_audio_duration:.2f} seconds")
    print(f"⏱ Original video duration: {original_duration:.2f} seconds")

    # Adjust VIDEO speed if needed
    adjusted_video_path = os.path.join(output_dir, "adjusted_video.mp4")
    adjust_video_speed(video_path, original_duration, new_audio_duration, adjusted_video_path)

    # Step 6: Merge with adjusted video
    output_video_path = os.path.join(output_dir, "final_translated_video.mp4")
    final_video = merge_audio_with_video(adjusted_video_path, new_audio_path, output_video_path)

    # Cleanup temporary files
    for temp_file in [extracted_audio_path, new_audio_path, adjusted_video_path]:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass

    print("🎉 Pipeline complete! Final video with translation ready!")
    return final_video

def download_youtube_video(youtube_url, output_dir):
    """Download YouTube video and return the path"""
    try:
        import yt_dlp
    except ImportError:
        raise ImportError("yt-dlp is not installed. Run: pip install yt-dlp")
    
    print("📥 Downloading YouTube video...")
    
    output_path = os.path.join(output_dir, "downloaded_video.mp4")
    
    ydl_opts = {
        'format': 'best[height<=720]/best',  # Prefer up to 720p
        'outtmpl': output_path,
        'quiet': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        print("✅ YouTube video downloaded successfully!")
        return output_path
    except Exception as e:
        print(f"❌ YouTube download failed: {e}")
        raise

def trim_video_to_first_minute(video_path, output_dir):
    """Trim video to first 1 minute (60 seconds)"""
    print("✂ Trimming video to first 1 minute...")
    
    output_path = os.path.join(output_dir, "trimmed_video.mp4")
    
    # Use FFmpeg to trim the video
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-ss', '0',  # Start from beginning
        '-t', '60',  # Duration of 60 seconds
        '-c', 'copy',  # Copy streams without re-encoding
        '-y',  # Overwrite output file
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ Video trimmed successfully to first 1 minute!")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"❌ Video trimming failed: {e}")
        # Fallback using moviepy
        print("🔄 Using MoviePy fallback for trimming...")
        from moviepy import VideoFileClip

        video = VideoFileClip(video_path)
        trimmed_video = video.subclipped(0, min(60, video.duration))
        trimmed_video.write_videofile(output_path, codec='libx264')
        video.close()
        trimmed_video.close()
        print("✅ Video trimmed successfully (MoviePy fallback)!")
        return output_path

def youtube_video_translation_pipeline(youtube_url, target_language, output_dir):
    """Complete pipeline: YouTube URL → Download → Trim to 1min → Translate"""
    print("🚀 Starting YouTube video translation pipeline...")
    
    # Step 1: Download YouTube video
    downloaded_video_path = download_youtube_video(youtube_url, output_dir)
    
    # Step 2: Trim video to first 1 minute
    trimmed_video_path = trim_video_to_first_minute(downloaded_video_path, output_dir)
    
    # Step 3: Run regular translation pipeline on trimmed video
    final_video = video_translation_pipeline(trimmed_video_path, target_language, output_dir)
    
    # Cleanup downloaded and trimmed files
    for temp_file in [downloaded_video_path, trimmed_video_path]:
        if os.path.exists(temp_file) and temp_file != final_video:
            try:
                os.remove(temp_file)
            except:
                pass
    
    print("🎉 YouTube video translation complete!")
    return final_video
