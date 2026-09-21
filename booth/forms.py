from django import forms

from .models import BoothSession


class BoothSessionForm(forms.ModelForm):
    class Meta:
        model = BoothSession
        fields = ("mode", "theme", "photo_filter", "layout", "caption")
        labels = {"photo_filter": "Filter", "caption": "Caption (optional)"}
        widgets = {
            "mode": forms.RadioSelect,
            "theme": forms.RadioSelect,
            "photo_filter": forms.RadioSelect,
            "layout": forms.RadioSelect,
            "caption": forms.TextInput(attrs={"placeholder": "e.g. 8,000 miles, same smile"}),
        }

    def __init__(self, *args, paired=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.paired = paired
        if not paired:
            self.initial["mode"] = BoothSession.Mode.SOLO

    def clean_mode(self):
        mode = self.cleaned_data["mode"]
        if mode == BoothSession.Mode.DUO and not self.paired:
            raise forms.ValidationError("Pair with your partner to use the booth together. The solo booth works right away.")
        return mode
