from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Profile
from .utils import is_valid_timezone, timezone_choices

User = get_user_model()


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Used only for password resets.")
    display_name = forms.CharField(
        max_length=60, required=False, help_text="What your partner calls you (optional)."
    )
    # Filled in by the browser (Intl API) so strips show the right local time.
    timezone = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_timezone(self):
        tz = self.cleaned_data.get("timezone") or "UTC"
        return tz if is_valid_timezone(tz) else "UTC"

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile = user.profile
            profile.display_name = self.cleaned_data.get("display_name", "")
            profile.timezone = self.cleaned_data["timezone"]
            profile.save()
        return user


class AccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("email",)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email


class ProfileForm(forms.ModelForm):
    timezone = forms.ChoiceField(choices=timezone_choices)

    class Meta:
        model = Profile
        fields = ("display_name", "city", "timezone", "avatar")
        labels = {"city": "City (shown on your strips)"}
        widgets = {"avatar": forms.ClearableFileInput(attrs={"accept": "image/*"})}

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and hasattr(avatar, "size") and avatar.size > settings.MAX_AVATAR_UPLOAD_SIZE:
            raise forms.ValidationError("Please choose an image under 3 MB.")
        return avatar
