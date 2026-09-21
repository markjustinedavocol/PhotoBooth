from django import forms

from .models import PhotoStrip


class StripNoteForm(forms.ModelForm):
    class Meta:
        model = PhotoStrip
        fields = ("caption", "love_note")
        labels = {"love_note": "Love note (on the back)"}
        widgets = {
            "love_note": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Write something for them to find when they flip it…"}
            ),
        }
