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


class AdminCreateCustomerForm(UserCreationForm):
    """Form for admins to create a customer account — no approval needed."""
    email   = forms.EmailField(required=True)
    phone   = forms.CharField(max_length=30, required=False, label='Phone')
    company = forms.CharField(max_length=150, required=False, label='Company')

    class Meta:
        model  = CustomUser
        fields = (
            'username', 'email', 'first_name', 'last_name',
            'phone', 'company', 'password1', 'password2',
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role   = CustomUser.ROLE_CUSTOMER
        user.status = CustomUser.STATUS_APPROVED
        if commit:
            user.save()
        return user


class AdminEditCustomerForm(forms.ModelForm):
    """Form for admins to edit a customer's profile details."""
    class Meta:
        model  = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'company')
