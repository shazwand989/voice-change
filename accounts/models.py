from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CUSTOMER = 'customer'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = [
        (ROLE_CUSTOMER, 'Customer'),
        (ROLE_ADMIN, 'Admin'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_DEACTIVATED = 'deactivated'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_DEACTIVATED, 'Deactivated'),
    ]

    role   = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CUSTOMER)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    phone   = models.CharField(max_length=30, blank=True)
    company = models.CharField(max_length=150, blank=True)

    def is_admin_role(self):
        return self.role == self.ROLE_ADMIN or self.is_superuser

    def is_approved(self):
        return self.status == self.STATUS_APPROVED or self.is_superuser

    def __str__(self):
        return self.username
