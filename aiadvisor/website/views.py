from django.views.decorators.csrf import csrf_exempt
from .models import Chat, Message
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import UserRegistrationForm, TranscriptUploadForm, UpdateUserForm
from django.conf import settings
from .models import User, Transcript, StudentCourse
from core.helpers import extract_info
from core.llm import ChatHistoryManager
import tempfile
import requests
import json
import html
import os
import io
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# Create your views here.
def home(request):
    string_test = 'Welcome to AI Advisor'
    return render(request, 'website/home.html', {'string_test':string_test})

def register(request):
    # POST means the user is sending data to our server.
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # Auto log in
            # ADDED BY KIRO AI -> TO FIX REDIRECTION FROM NEW FRONTEND
            messages.success(request, 'Account created successfully!')
            return redirect('dashboard') # Send to dashboard
        else:
            # Add error messages for debugging
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = UserRegistrationForm()

    return render(request, 'website/register.html', {'form': form})

def logout_view(request):
    """Handle logout and redirect to home"""
    logout(request)
    return redirect('home')

@login_required(login_url='login')
def dashboard(request):
    curr_user = request.user

    # Check if the user has a transcript
    try:
        transcript = curr_user.transcript
        has_transcript = True
    except Transcript.DoesNotExist:
        transcript = None
        has_transcript = False

    # If they have a transcript, get their courses and info
    if has_transcript:
        courses = transcript.courses.all()
        
        # ADDED BY KIRO AI -> TO BE ABLE TO DISPLAY GPA INFORMATION IN BROWSER
        # Calculate semester statistics
        from collections import defaultdict
        semester_stats = defaultdict(lambda: {'courses': [], 'total_credits': 0, 'quality_points': 0, 'gpa': 0})
        
        # Grade to GPA mapping
        grade_map = {
            'A': 4.0, 'A-': 3.7,
            'B+': 3.3, 'B': 3.0, 'B-': 2.7,
            'C+': 2.3, 'C': 2.0, 'C-': 1.7,
            'D+': 1.3, 'D': 1.0, 'D-': 0.7,
            'F': 0.0
        }
        
        for course in courses:
            term = course.term
            semester_stats[term]['courses'].append(course)
            
            # Only count credits and GPA for non-transfer, non-withdrawn courses
            if course.term != 'Transfer Credit' and course.letter_grade not in ['W', 'IP']:
                credits = float(course.credit_hours)
                semester_stats[term]['total_credits'] += credits
                
                # Calculate quality points if grade is in map
                if course.letter_grade in grade_map:
                    semester_stats[term]['quality_points'] += credits * grade_map[course.letter_grade]
        
        # Calculate GPA for each semester
        for term in semester_stats:
            if semester_stats[term]['total_credits'] > 0:
                semester_stats[term]['gpa'] = round(
                    semester_stats[term]['quality_points'] / semester_stats[term]['total_credits'], 
                    2
                )
        
        context = {
            'first_name': curr_user.first_name,
            'last_name': curr_user.last_name,
            'username': curr_user.username,
            'major': transcript.major,
            'minor': transcript.minor, # Default ''
            'concentration': transcript.concentration, # Default ''
            'gpa': transcript.gpa,
            'total_credits': transcript.total_credits,
            'courses': courses,
            'semester_stats': dict(semester_stats),
            'has_transcript': True
        }
    else:
        context = {
            'first_name': curr_user.first_name,
            'last_name': curr_user.last_name,
            'username': curr_user.username,
            'has_transcript': False
        }

    return render(request, 'website/dashboard.html', context)

@login_required(login_url='login')
def upload_transcript(request):
    if request.method == 'POST' and request.FILES.get('transcript_pdf'):
        pdf_file = request.FILES['transcript_pdf'] # This is us grabbing the uploaded transcript

        # Now lets check that it is a pdf file
        if not pdf_file.name.endswith('.pdf'):
            messages.error(request, 'Please upload a PDF file.')
            return redirect('dashboard')
        
        # TODO: Maybe check for filetypes?

        # Save PDF to a temporary location for parsing
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            for chunk in pdf_file.chunks():
                tmp_file.write(chunk)
            tmp_path = tmp_file.name

        # Now lets run our parser on the transcript
        try:
            
            # Decide where to save the parsed transcript JSON for this user
            transcript_dir = settings.BASE_DIR / "transcripts"
            transcript_dir.mkdir(parents=True, exist_ok=True)
            
            transcript_json_path = transcript_dir / f"{request.user.id}.json"

            # Parse + save JSON (same schema as sample1.json)
            student_info = extract_info(tmp_path, save=str(transcript_json_path))

            # Confirm the name matches the user
            parsed_name = student_info.get('name', '')
            user_full_name = f"{request.user.first_name} {request.user.last_name}"
            if parsed_name.lower().strip() != user_full_name.lower().strip():
                messages.error(request, f'Name mismatch: Transcript shows "{parsed_name}" but account shows "{user_full_name}"')
                return redirect('dashboard')
            
            # Delete old transcript if exists
            if hasattr(request.user, 'transcript'):
                request.user.transcript.delete()

            # Get total credits and quality points from student_info
            total_credits = student_info['earned_credits']
            total_quality_points = student_info['quality_points']
            
            print(f"DEBUG - Total Credits: {total_credits}")
            print(f"DEBUG - Total Quality Points: {total_quality_points}")

            # Get GPA from student_info
            gpa = student_info['gpa']

            print(f"DEBUG - Calculated GPA: {gpa}")

            # Now we can create the Transcript object for this user
            transcript = Transcript.objects.create(
                user=request.user,
                major=student_info.get('major', ''),
                minor=student_info.get('minor', ''),
                concentration=student_info.get('concentration', ''),
                gpa=round(gpa, 3),
                total_credits=int(total_credits)
            )

            # Handle TRANSFER courses 
            if 'transfer' in student_info:
                for course in student_info['transfer']:
                    StudentCourse.objects.create(
                        transcript=transcript,
                        title=course['title'],
                        letter_grade=course['grade'],
                        passed=True,
                        credit_hours=float(course['credits']),
                        level='Transfer',
                        term='Transfer Credit',
                        description=''
                    )

            # Handle in-progress courses
            if 'inprogress' in student_info:
                for term_data in student_info['inprogress']:
                    term = term_data['term']
                    for course in term_data['courses']:
                        StudentCourse.objects.create(
                            transcript=transcript,
                            title=course['title'],
                            letter_grade='IP',  # In Progress
                            passed=False,  # Not completed yet
                            credit_hours=float(course['credits']),
                            level=course['level'],
                            term=term,
                            description='In Progress'
                        )

            # Handle completed courses
            if 'completed' in student_info:
                for term_data in student_info['completed']:
                    term = term_data['term']
                    for course in term_data['courses']:
                        grade = course['grade']
                        passed = grade not in ['F', 'W']

                        StudentCourse.objects.create(
                            # TODO: Talk to AI team about if we need the ID of the course to be the CRN for context
                            transcript=transcript,
                            title=course['title'],
                            letter_grade=grade,
                            passed=passed,
                            credit_hours=float(course['credits']),
                            level=course['level'],
                            term=term,
                            # TODO: Access descriptions somewhere
                            description=''
                        )

            
            messages.success(request, 'Transcript uploaded succesfully.')
            return redirect('dashboard')
        
        except AssertionError as e:
            messages.error(request, f'Invalid transcript format: {str(e)}')
            return redirect('dashboard')
        
        except Exception as e:
            messages.error(request, f'Error processing transcript: {str(e)}')

        finally:
            # Clean up our temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return redirect('dashboard')

@login_required(login_url='login')
def user_settings(request):
    curr_user = request.user
    if request.method == 'POST':
        username_form = UpdateUserForm(request.POST, instance=request.user)
        if username_form.is_valid():
            username_form.save()
            return redirect('login')

    else:
        username_form = UpdateUserForm(instance=request.user)


    context = {
        'username': curr_user.username,
        'username_form': username_form,
        'first_name': curr_user.first_name,
        'last_name': curr_user.last_name
    }
    return render(request, 'website/settings.html', context)

@login_required(login_url='login')
def clear_chat(request):
    """Clear chat history for the current user ONLY"""
    chat, _ = Chat.objects.get_or_create(user=request.user)

    # Security check: Ensure chat belongs to current user
    if chat.user != request.user:
        return JsonResponse({"error": "Unauthorized access"}, status=403)

    # Delete only messages from current user's chat
    Message.objects.filter(chat=chat, chat__user=request.user).delete()
    return redirect('chat_page')

@login_required(login_url='login')
def chat_page(request):
    """Main chat interface for the logged-in user"""
    # Get or create chat for current user ONLY
    chat, _ = Chat.objects.get_or_create(user=request.user)

    # Explicitly filter messages by current user's chat
    messages = Message.objects.filter(chat=chat, chat__user=request.user).order_by('timestamp')

    return render(request, 'website/chat.html', {'chat': chat, 'messages': messages})

@csrf_exempt
@login_required(login_url='login')
def send_message(request):
    """Handles HTMX postbacks when user sends a message"""
    if request.method == "POST":
        user_message = request.POST.get("message", "").strip()
        if not user_message:
            return HttpResponse("")  # nothing to process

        chat, _ = Chat.objects.get_or_create(user=request.user)

        # Save the user's message
        Message.objects.create(
            chat=chat,
            role="User",
            content=user_message,
            timestamp=timezone.now()
        )

        # Extract message history using ChatHistoryManager (last 10 pairs = 20 messages)
        # SECURITY: Explicitly query messages for current user only
        user_messages = Message.objects.filter(
            chat=chat,
            chat__user=request.user
        ).select_related('chat', 'chat__user')

        message_history = ChatHistoryManager.extract_message_history(
            user_messages,
            user_id=request.user.id,
            limit=20
        )

        # Get the transcript for this user
        transcript_dir = settings.BASE_DIR / "transcripts"
        transcript_dir.mkdir(parents=True, exist_ok=True)

        transcript_json_path = transcript_dir / f"{request.user.id}.json"
        transcript = json.loads(open(transcript_json_path, "r").read())

        def generate_response():
            response = requests.post(
                settings.AGENT_SERVER + "/chat",
                json={"messages": message_history, "transcript": transcript},
                stream=True
            )

            ai_response_text = ""
            for chunk in response.iter_content(chunk_size=None):
                if not chunk:
                    continue
                text = chunk.decode("utf-8")
                ai_response_text += text
                yield text

            # Save the AI's response
            Message.objects.create(
                chat=chat,
                role="AI",
                content=ai_response_text,
                timestamp=timezone.now()
            )

        return StreamingHttpResponse(generate_response(), content_type="text/plain")


    return JsonResponse({"error": "Invalid request"}, status=400)
    
def _clean_chat_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\[THINKING\][\s\S]*?\[\/THINKING\]", "", text)
    text = text.replace("[AI RESPONSE]", "").replace("[/AI RESPONSE]", "")
    return text.strip()

@login_required(login_url="login")
def export_chat_pdf(request):
    chat, _ = Chat.objects.get_or_create(user=request.user)
    msgs = chat.messages.all()  # already ordered by Meta.ordering

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="AI Academic Advisor - Chat Export",
        author=str(request.user.username),
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    meta_style = styles["Normal"]
    role_style = ParagraphStyle("RoleHeader", parent=styles["Heading4"], spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle("Body", parent=styles["BodyText"], leading=14, spaceAfter=8)

    story = []
    story.append(Paragraph("AI Academic Advisor — Chat History", title_style))
    story.append(Paragraph(f"User: {request.user.username}", meta_style))
    story.append(Paragraph(f"Exported: {timezone.now().strftime('%Y-%m-%d %H:%M')}", meta_style))
    story.append(Spacer(1, 12))

    if not msgs.exists():
        story.append(Paragraph("No messages to export.", body_style))
    else:
        for m in msgs:
            ts = m.timestamp.strftime("%Y-%m-%d %H:%M") if m.timestamp else ""
            role = (m.role or "Unknown").strip()
            content = _clean_chat_text(m.content)

            safe = (content or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            safe = safe.replace("\n", "<br/>")

            story.append(Paragraph(f"{role} <font size=9 color='#666666'>({ts})</font>", role_style))
            story.append(Paragraph(safe if safe else "<i>(empty)</i>", body_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = f"chat_history_{request.user.username}_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

