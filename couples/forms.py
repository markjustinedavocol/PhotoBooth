from django import forms

from .models import Couple


class JoinForm(forms.Form):
    code = forms.CharField(
        max_length=16,
        label="Partner's invite code",
        widget=forms.TextInput(attrs={"placeholder": "e.g. K7PX4MQA", "autocomplete": "off"}),
    )


class CoupleSettingsForm(forms.ModelForm):
    class Meta:
        model = Couple
        fields = ("anniversary", "next_meetup")
        labels = {"anniversary": "Our anniversary", "next_meetup": "Next time we meet"}
        widgets = {
            "anniversary": forms.DateInput(attrs={"type": "date"}),
            "next_meetup": forms.DateInput(attrs={"type": "date"}),
        }
