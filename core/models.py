from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django.utils import timezone
class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('moderator', 'Moderator'),
        ('contributor', 'Contributor')
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='contributor')
    email = models.CharField(max_length=20)
    groups = models.ManyToManyField(Group, related_name="core_user_groups", blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name="core_user_permissions", blank=True)
    created_at = models.DateTimeField(auto_now_add=True) 
    class Meta:
        permissions = [
            ("can_manage_users", "Can manage users"),
        ]
class Word(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('review', 'In Review'),
        ('approved', 'Approved')
    ]
    text = models.CharField(max_length=100, unique=True)
    definition = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    examples = models.TextField(blank=True, null=True) 
    
    def __str__(self):
        return self.text

class WordHistory(models.Model):
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='history')
    previous_status = models.CharField(max_length=20, choices=Word.STATUS_CHOICES)
    new_status = models.CharField(max_length=20, choices=Word.STATUS_CHOICES)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.word.text}: {self.previous_status} → {self.new_status}"


class ApprovalWorkflow(models.Model):
    word = models.OneToOneField(Word, on_delete=models.CASCADE)
    comments = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Word.STATUS_CHOICES, default='pending')
    updated_at = models.DateTimeField(auto_now=True)

class Contribution(models.Model):
    ACTION_CHOICES = [
        ('add', 'Add'),
        ('edit', 'Edit'),
        ('delete', 'Delete'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    word = models.ForeignKey(Word, on_delete=models.CASCADE)
    action = models.CharField(max_length=50)  # Added, Edited, Approved
    timestamp = models.DateTimeField(auto_now_add=True)
    
   
    

class RootWord(models.Model):
    text = models.CharField(max_length=100, unique=True)
    definition = models.TextField(blank=True, null=True)
    translated = models.BooleanField(default=False)

class PointsSystem(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    points = models.IntegerField(default=0)
    badges = models.TextField(blank=True, null=True)  # JSON field to store badge info
    def __str__(self):
        return f"{self.user.username} - {self.points} points"
class ModeratorComment(models.Model):
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='moderator_comments')
    moderator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='moderator_comments')
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.moderator.username} on {self.word.text}"