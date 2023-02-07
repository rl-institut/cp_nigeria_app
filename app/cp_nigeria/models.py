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
    USERS = (("HH", "Household"),
             ("E", "Enterprise"),
             ("PF", "Public facility"),
             ("HF", "Health facility"))
    user_type = models.CharField(max_length=120, choices=USER_TYPES)

    def __str__(self):
        return self.user_type


class FacilityType(models.Model):
    ENTERPRISES = (("F", "Food"),
                   ("R", "Retail"),
                   ("T", "Trades"),
                   ("E-D", "Digital"),
                   ("A", "Agricultural"))

    PUBLIC_FACILITIES = (("School", "School"),
                         ("Mosque", "Mosque"),
                         ("Church", "Church"),
                         ("Government building", "Government building"),
                         ("Town Hall", "Town Hall"))

    HEALTH_FACILITIES = (("Health Center", "Health Center"),
                         ("Dispensary/Pharmacy", "Dispensary/Pharmacy"),
                         ("Clinic", "Clinic"),
                         ("Hospital", "Hospital"))

    user_type = models.ForeignKey(UserType, on_delete=models.CASCADE)
    facility_type = models.CharField(max_length=120)

    def __str__(self):
        return self.facility_type


class UserGroup(models.Model):
    # TODO create foreignkey dependencies
    TIERS = (("Tier 1", "Tier 1"),
             ("Tier 2", "Tier 2"))

    user_type = models.CharField(max_length=120, choices=USER_TYPES)
    tier = models.CharField(max_length=30, choices=TIERS)
    number_users = models.IntegerField()


