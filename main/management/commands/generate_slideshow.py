"""
Management command to generate a slideshow for a pending slideshow object.
Usage: python manage.py generate_slideshow <slideshow_id>
"""
from django.core.management.base import BaseCommand
from main.models import SlideShow
from main.utils.slideshow_generator import generate_slideshow


class Command(BaseCommand):
    help = 'Generate a video slideshow from uploaded photos'

    def add_arguments(self, parser):
        parser.add_argument('slideshow_id', type=int, help='ID of the slideshow to generate')

    def handle(self, *args, **options):
        slideshow_id = options['slideshow_id']
        try:
            slideshow = SlideShow.objects.get(id=slideshow_id)
        except SlideShow.DoesNotExist:
            self.stderr.write(f'Slideshow {slideshow_id} not found')
            return

        self.stdout.write(f'Generating slideshow: {slideshow.title}...')
        photos = slideshow.photos.all()
        self.stdout.write(f'Using {photos.count()} photos')

        result = generate_slideshow(slideshow, photos)

        if result:
            self.stdout.write(self.style.SUCCESS(f'Slideshow generated: {result}'))
        else:
            self.stderr.write(f'Failed: {slideshow.error_message}')
