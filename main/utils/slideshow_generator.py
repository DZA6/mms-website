"""
Slideshow generator — creates HD video tributes from uploaded photos.
Uses moviepy for video composition with crossfade transitions and optional music.
"""
import os
import random
from pathlib import Path

from django.conf import settings

try:
    from moviepy import (
        ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips,
        VideoClip
    )
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False


# Built-in royalty-free funeral-appropriate music options
# (These would be actual audio files in production)
MUSIC_OPTIONS = {
    'gentle-piano': 'Gentle Piano',
    'strings': 'Soft Strings',
    'acoustic': 'Warm Acoustic',
    'ambient': 'Peaceful Ambient',
}


def get_default_music_path(choice='gentle-piano'):
    """Return path to music file. Currently placeholder — returns None for silent."""
    music_dir = Path(settings.MEDIA_ROOT) / 'music'
    # In production, place .mp3 files here matching the keys above
    music_file = music_dir / f'{choice}.mp3'
    if music_file.exists():
        return str(music_file)
    return None


def generate_slideshow(slideshow_obj, photo_queryset, progress_callback=None):
    """
    Generate a video slideshow from photos.

    Args:
        slideshow_obj: SlideShow model instance (updated with status)
        photo_queryset: QuerySet of Photo objects
        progress_callback: Optional function(slideshow_obj, progress_float)

    Returns:
        Path to generated video file, or None on failure
    """
    if not MOVIEPY_AVAILABLE:
        slideshow_obj.status = 'failed'
        slideshow_obj.error_message = 'moviepy library not installed'
        slideshow_obj.save()
        return None

    # Mark as generating
    slideshow_obj.status = 'generating'
    slideshow_obj.save()

    try:
        photos = list(photo_queryset)
        if not photos:
            raise ValueError('No photos to include in slideshow')

        # For production: add watermark overlay, title cards, etc.
        clips = []
        total = len(photos)

        for i, photo in enumerate(photos):
            if not os.path.exists(photo.image.path):
                continue

            # Create image clip with crossfade
            clip = ImageClip(str(photo.image.path), duration=3.5)
            clip = clip.resized(width=1920)  # HD width

            # Center-crop if too tall
            if clip.h > 1080:
                clip = clip.resized(height=1080)

            # Add crossfade
            clip = clip.with_effects([vfx.CrossFadeIn(0.5)])
            clips.append(clip)

            if progress_callback:
                progress_callback(slideshow_obj, (i + 1) / total)

        if not clips:
            raise ValueError('No valid photos could be processed')

        # Concatenate all clips
        final = concatenate_videoclips(clips, method='compose')

        # Try to add background music
        music_path = get_default_music_path(slideshow_obj.music_choice)
        if music_path:
            try:
                audio = AudioFileClip(music_path)
                # Loop or trim audio to match video length
                if audio.duration < final.duration:
                    audio = audio.with_duration(final.duration)
                else:
                    audio = audio.subclipped(0, final.duration)
                # Fade audio in/out
                audio = audio.with_effects([
                    vfx.FadeIn(2),
                    vfx.FadeOut(3),
                ])
                final = final.with_audio(audio)
            except Exception:
                pass  # Silent if music fails

        # Ensure output directory exists
        output_dir = Path(settings.MEDIA_ROOT) / 'slideshows'
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = str(output_dir / f'slideshow_{slideshow_obj.id}.mp4')

        # Write video file
        final.write_videofile(
            output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            preset='medium',
            threads=2,
            logger=None,  # Suppress moviepy output
        )

        # Clean up
        final.close()

        # Update model
        slideshow_obj.status = 'completed'
        slideshow_obj.video_file = f'slideshows/slideshow_{slideshow_obj.id}.mp4'
        slideshow_obj.save()

        return output_path

    except Exception as e:
        slideshow_obj.status = 'failed'
        slideshow_obj.error_message = str(e)
        slideshow_obj.save()
        return None


# Import vfx after moviepy import
if MOVIEPY_AVAILABLE:
    from moviepy import vfx
else:
    vfx = None
