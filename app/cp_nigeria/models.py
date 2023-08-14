from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from datetime import timedelta
from django.forms.models import model_to_dict
from django.utils.translation import gettext_lazy as _

USER_TYPES = (("Household", "Household"),
              ("Food", "Enterprise: Food"),
              ("Retail", "Enterprise: Retail"),
              ("Trades", "Enterprise: Trades"),
              ("Digital", "Enterprise: Digital"),
              ("Agricultural", "Enterprise: Agricultural"),
              ("School", "Public facility: School"),
              ("Mosque", "Public facility: Mosque"),
              ("Church", "Public facility: Church"),
              ("Government building", "Public facility: Government building"),
              ("Town Hall", "Public facility: Town Hall"),
              ("Health Center", "Health facility: Health Center"),
              ("Dispensary/Pharmacy", "Health facility: Dispensary/Pharmacy"),
              ("Clinic", "Health facility: Clinic"),
              ("Hospital", "Health facility: Hospital"))


class Project(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    date_start = models.DateTimeField()
    date_end = models.DateTimeField()

    def __str__(self):
        return self.name


class UserType(models.Model):
    user_type = models.CharField(max_length=50)

    def __str__(self):
        return self.user_type


class FacilityType(models.Model):
    user_type = models.ForeignKey(UserType, on_delete=models.CASCADE)
    facility_type = models.CharField(max_length=100)

    def __str__(self):
        return self.facility_type


class UserGroup(models.Model):
    TIERS = (("Low", "Low"),
             ("Middle", "Middle"),
             ("High", "High"))

    user_type = models.ForeignKey(UserType, on_delete=models.CASCADE)
    facility_type = models.ForeignKey(FacilityType, on_delete=models.CASCADE)
    tier = models.CharField(max_length=30, choices=TIERS)
    number_users = models.IntegerField()


