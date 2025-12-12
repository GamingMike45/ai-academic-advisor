from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid

# Create your models here.
class User(AbstractUser):
    user_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        db_table = 'users'

class Transcript(models.Model):
    transcript_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='transcript') # To get transcript: user.transcript

    major = models.CharField(max_length=200)
    minor = models.CharField(max_length=200, blank=True, default='')
    concentration = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    gpa = models.DecimalField(max_digits=4, decimal_places=3)
    total_credits = models.IntegerField()

    def __str__(self):
        return str(self.transcript_id)

    class Meta:
        db_table = 'transcripts'

class StudentCourse(models.Model):
    course_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE, related_name='courses') # To get all courses: transcript.courses.all()

    title = models.CharField(max_length=200)
    letter_grade = models.CharField(max_length=5) # 'A-', 'B+'
    passed = models.BooleanField()
    credit_hours = models.DecimalField(max_digits=4, decimal_places=3)
    level = models.CharField(max_length=100)
    term = models.CharField(max_length=50)
    description = models.TextField(blank=True, default='')

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'studentcourses'

class Chat(models.Model):
    chat_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='chat') # To get transcript: user.chat
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.chat_id)

    class Meta:
        db_table = 'chats'

class Message(models.Model):
    message_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages') # To get all msgs: chat.messages.all()

    role = models.CharField(max_length=20) # 'User' or 'AI'
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.content

    class Meta:
        db_table = 'messages'
        ordering = ['timestamp']
