from django import forms

from .models import BoothSession


class BoothSessionForm(forms.ModelForm):
    class Meta:
        model = BoothSession
        fields = ("theme", "photo_filter", "layout", "caption")
        labels = {"photo_filter": "Filter", "caption": "Caption (optional)"}
        widgets = {
            "theme": forms.RadioSelect,
            "photo_filter": forms.RadioSelect,
            "layout": forms.RadioSelect,
            "caption": forms.TextInput(attrs={"placeholder": "e.g. 8,000 miles, same smile"}),
        }
