from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser


class RegisterForm(UserCreationForm):
    email   = forms.EmailField(required=True)
    phone   = forms.CharField(max_length=30, required=False, label='Phone')
    company = forms.CharField(max_length=150, required=False, label='Company')

    class Meta:
        model  = CustomUser
        fields = (
            'username', 'email', 'first_name', 'last_name',
            'phone', 'company', 'password1', 'password2',
        )
