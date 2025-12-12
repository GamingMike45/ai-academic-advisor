from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.password_validation import validate_password
from .models import User

# This is the form for creating a user in the register.html endpoint.
class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']

# This is the code for uploading a transcript
class TranscriptUploadForm(forms.Form):
    transcript_pdf = forms.FileField(
        label='Upload Transcript',
        help_text='Upload your official transcript in PDF format'
    )

#Form for settings page
class UpdateUserForm(UserChangeForm):
    password = None #Prevents the return of the hashed password
    password1 = forms.CharField(required=False, widget = forms.PasswordInput, label= "Enter new password")
    password2 = forms.CharField(required=False, widget = forms.PasswordInput, label= "Comfirm new password")

    class Meta:
        model = User
        fields = ['username', 'password1', 'password2']

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')

        if (p1 or p2):
            if (p1 != p2):
                raise forms.ValidationError("Passwords do not match")
            validate_password(p1, self.instance)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        p1=self.cleaned_data.get('password1')
        if (p1):
            user.set_password(p1)
        if commit:
            user.save()
        return user
    
    def __init__(self, *args, **kwargs): #makes username field not required
        super().__init__(*args, **kwargs)
        self.fields["username"].required = False
