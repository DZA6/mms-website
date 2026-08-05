from django import forms
from django.forms import ClearableFileInput
from django.utils.datastructures import MultiValueDict
from .models import Photo


class MultipleFileInput(ClearableFileInput):
    """File input that supports selecting multiple files."""
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Field that handles multiple uploaded files."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, MultiValueDict)):
            return [single_clean(d, initial) for d in data]
        return [single_clean(data, initial)]


class PhotoForm(forms.ModelForm):
    """Single photo upload form (kept for backward compat)."""
    class Meta:
        model = Photo
        fields = ['title', 'image']


class BulkPhotoForm(forms.Form):
    """Accept a batch title + multiple image files at once."""
    title = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': "e.g. Mom's Celebration of Life"})
    )
    images = MultipleFileField(label='Photos')


class BusinessMediaForm(forms.Form):
    """Business portal upload: photos + videos attached to a specific order."""
    order = forms.ModelChoiceField(
        queryset=None,  # set per-request in the view
        label="Customer Order",
        empty_label="— Select the order —",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    photo_title = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={'placeholder': "e.g. Smith Family Photos"}),
    )
    images = MultipleFileField(label='Photos', required=False)
    video_title = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={'placeholder': "e.g. Interview footage"}),
    )
    videos = MultipleFileField(label='Videos', required=False)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('images') and not cleaned.get('videos'):
            raise forms.ValidationError("Upload at least one photo or one video.")
        return cleaned