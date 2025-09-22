from django.db import models

class SiteSettings(models.Model):
    application_name = models.CharField(max_length=100, default="MagicTales AI")
    application_logo = models.ImageField(upload_to='logos/', null=True, blank=True)
    default_language = models.CharField(max_length=20, default="English")
    timezone = models.CharField(max_length=100, default="UTC")

    def save(self, *args, **kwargs):
        self.pk = 1
        super(SiteSettings, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Site Application Settings"