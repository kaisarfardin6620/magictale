from django.db import models

class FAQItem(models.Model):
    class Category(models.TextChoices):
        GETTING_STARTED = 'getting_started', 'Getting Started'
        SUBSCRIPTION = 'subscription', 'Subscription & Billing'
        PARENTAL = 'parental', 'Parental Controls'
        TECHNICAL = 'technical', 'Technical Issues'

    category = models.CharField(max_length=50, choices=Category.choices)
    question = models.CharField(max_length=255)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0, help_text="Order to display items (lower numbers first).")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.question