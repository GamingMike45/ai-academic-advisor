from django.contrib import admin
from .models import User, Transcript, StudentCourse, Chat, Message

# Register your models here.
admin.site.register(User)
admin.site.register(Transcript)
admin.site.register(StudentCourse)
admin.site.register(Chat)
admin.site.register(Message)