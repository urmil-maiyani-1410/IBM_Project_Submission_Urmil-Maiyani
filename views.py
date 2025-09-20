from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone
from django.urls import reverse
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import *
import random
import string
import numpy as np
from PIL import Image
import os
import uuid
import io
import requests
from sklearn.decomposition import PCA

def LandingView(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')
        ip_address = get_client_ip(request)
        
        try:
            Contact.objects.create(
                name=name,
                email=email,
                message=message,
                ip_address=ip_address
            )
            
            email_subject = f'New Contact Form Submission from {name}'
            email_body = f'Name: {name}\nEmail: {email}\nMessage: {message}'
            email = EmailMessage(
                email_subject,
                email_body,
                settings.EMAIL_HOST_USER,
                [settings.EMAIL_HOST_USER],
                reply_to=[email]
            )
            email.send()
            
            messages.success(request, "Thank you for your message. We'll get back to you soon!")
        except Exception as e:
            messages.error(request, "Sorry, there was an error sending your message. Please try again later.")
        
        return redirect('landing')
    
    return render(request, 'landing.html')

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

@login_required
def Home(request):
    return render(request, 'index.html')

def RegisterView(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        ip_address = get_client_ip(request)

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists!")
            return redirect('register')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists!")
            return redirect('register')

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        user.is_active = False
        user.save()

        verification = EmailVerification.objects.create(user=user)
        verification_link = f"{request.scheme}://{request.get_host()}{reverse('verify-email', args=[str(verification.token)])}"

        email_subject = "Verify your email - AI Compress"
        email_body = f"""
        Hi {user.first_name},

        Thank you for registering with AI Compress. To complete your registration, please click the link below:

        {verification_link}

        This link will expire in 24 hours.

        Best regards,
        AI Compress Team
        """

        email = EmailMessage(
            email_subject,
            email_body,
            settings.EMAIL_HOST_USER,
            [user.email],
        )
        email.send(fail_silently=False)

        RegistrationAttempt.objects.create(
            ip_address=ip_address,
            was_successful=True
        )

        messages.success(request, "Registration successful! Please check your email to verify your account.")
        return redirect('login')

    return render(request, 'register.html')

def VerifyEmailView(request, token):
    try:
        verification = EmailVerification.objects.get(token=token)
        user = verification.user

        if verification.is_verified:
            messages.info(request, "Email already verified. You can now login.")
            return redirect('login')

        if verification.is_expired:
            verification.token = uuid.uuid4()
            verification.created_at = timezone.now()
            verification.save()

            verification_link = f"{request.scheme}://{request.get_host()}{reverse('verify-email', args=[str(verification.token)])}"
            
            email_subject = "New Verification Link - AI Compress"
            email_body = f"""
            Hi {user.first_name},

            Your previous verification link has expired. Here's your new verification link:

            {verification_link}

            This link will expire in 24 hours.

            Best regards,
            AI Compress Team
            """

            email = EmailMessage(
                email_subject,
                email_body,
                settings.EMAIL_HOST_USER,
                [user.email],
            )
            email.send(fail_silently=False)

            messages.error(request, "Verification link expired! We've sent you a new one.")
            return redirect('login')

        verification.is_verified = True
        verification.save()
        user.is_active = True
        user.save()
        messages.success(request, "Email verified successfully! You can now login.")
        return redirect('login')

    except EmailVerification.DoesNotExist:
        messages.error(request, "Invalid verification link!")
        return redirect('login')

def LoginView(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        ip_address = get_client_ip(request)

        try:
            user = User.objects.get(username=username)
            
            try:
                verification = EmailVerification.objects.get(user=user)
                if not verification.is_verified:
                    messages.error(request, "Please verify your email first! Check your inbox for the verification link.")
                    LoginAttempt.objects.create(
                        ip_address=ip_address,
                        username=username,
                        was_successful=False
                    )
                    return redirect('login')
            except EmailVerification.DoesNotExist:
                messages.error(request, "Please verify your email first!")
                LoginAttempt.objects.create(
                    ip_address=ip_address,
                    username=username,
                    was_successful=False
                )
                return redirect('login')

            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                LoginAttempt.objects.create(
                    ip_address=ip_address,
                    username=username,
                    was_successful=True
                )
                ActivityLog.objects.create(
                    user=user,
                    activity_type='LOGIN',
                    ip_address=ip_address,
                    details="User logged in"
                )
                return redirect('home')
            else:
                messages.error(request, "Invalid password!")
                LoginAttempt.objects.create(
                    ip_address=ip_address,
                    username=username,
                    was_successful=False
                )
        except User.DoesNotExist:
            messages.error(request, "Username does not exist!")
            LoginAttempt.objects.create(
                ip_address=ip_address,
                username=username,
                was_successful=False
            )
        
        return redirect('login')

    return render(request, 'login.html')
    
def LogoutView(request):
    if request.user.is_authenticated:
        ActivityLog.objects.create(
            user=request.user,
            activity_type='LOGOUT',
            ip_address=get_client_ip(request),
            details="User logged out"
        )
    logout(request)
    return redirect('landing')

def ForgotPassword(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        ip_address = get_client_ip(request)
        
        try:
            user = User.objects.get(email=email)
            reset_obj = PasswordReset.objects.create(user=user)
            
            reset_link = f"{request.scheme}://{request.get_host()}{reverse('reset-password', args=[str(reset_obj.reset_id)])}"
            
            email_body = f"Hi {user.username},\n\nPlease click on the link below to reset your password:\n\n{reset_link}\n\nThis link will expire in 10 minutes.\n\nBest regards,\nAI Compress Team"
            
            email = EmailMessage(
                'Password Reset Request',
                email_body,
                settings.EMAIL_HOST_USER,
                [user.email],
            )
            email.send()
            
            ActivityLog.objects.create(
                user=user,
                activity_type='PASSWORD_RESET',
                ip_address=ip_address,
                details="Password reset requested"
            )
            
            return redirect('password-reset-sent', reset_id=reset_obj.reset_id)
        except User.DoesNotExist:
            messages.error(request, 'No user found with this email address!')
        except Exception as e:
            messages.error(request, str(e))
    
    return render(request, 'forgot_password.html')

def PasswordResetSent(request, reset_id):
    return render(request, 'password_reset_sent.html')

def ResetPassword(request, reset_id):
    try:
        reset_obj = PasswordReset.objects.get(reset_id=reset_id)
        
        if timezone.now() > reset_obj.created_when + timezone.timedelta(minutes=10):
            messages.error(request, 'Password reset link has expired!')
            return redirect('forgot-password')
        
        if request.method == 'POST':
            password = request.POST.get('password')
            confirm_password = request.POST.get('confirm_password')
            
            if password != confirm_password:
                messages.error(request, 'Passwords do not match!')
                return render(request, 'reset_password.html')
            
            user = reset_obj.user
            user.set_password(password)
            user.save()
            
            ActivityLog.objects.create(
                user=user,
                activity_type='PASSWORD_CHANGE',
                ip_address=get_client_ip(request),
                details="Password reset completed"
            )
            
            reset_obj.delete()
            messages.success(request, 'Password reset successful! Please login with your new password.')
            return redirect('login')
        
        return render(request, 'reset_password.html')
    except PasswordReset.DoesNotExist:
        messages.error(request, 'Invalid password reset link!')
        return redirect('forgot-password')

@login_required
def CompressView(request):
    if request.method == "POST" and request.FILES.get("fileInput"):
        uploaded_file = request.FILES["fileInput"]
        ip_address = get_client_ip(request)

        # Check file size (10MB = 10 * 1024 * 1024 bytes)
        if uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, "File size exceeds 10MB limit!")
            return JsonResponse({"success": False, "error": "File size exceeds 10MB limit"})

        # Log the upload action
        ActivityLog.objects.create(
            user=request.user,
            activity_type='UPLOAD',
            ip_address=ip_address,
            details=f"User uploaded image: {uploaded_file.name} ({uploaded_file.size / 1024:.2f} KB)"
        )

        # Compress the image using optimized JPEG compression
        try:
            original_array, compressed_array, compressed_path = compress_image_with_jpeg(uploaded_file)

            # Calculate file sizes
            original_size = uploaded_file.size / 1024  # in KB
            absolute_compressed_path = os.path.join(settings.MEDIA_ROOT, compressed_path)
            if not os.path.exists(absolute_compressed_path):
                raise FileNotFoundError(f"Compressed file not found at {absolute_compressed_path}")
            compressed_size = os.path.getsize(absolute_compressed_path) / 1024  # in KB

            # Log the compression and save action
            ActivityLog.objects.create(
                user=request.user,
                activity_type='COMPRESSION',
                ip_address=ip_address,
                details=f"Image compressed from {original_size:.2f} KB to {compressed_size:.2f} KB using JPEG and saved at {compressed_path}"
            )

            # Generate the URL for the compressed image
            compressed_url = default_storage.url(compressed_path)
            print(f"Compressed URL: {compressed_url}")  # Debug print

            # Prepare response data
            response_data = {
                "original_size": f"{original_size:.2f}",
                "compressed_size": f"{compressed_size:.2f}",
                "compressed_url": compressed_url,
                "success": True
            }
            return JsonResponse(response_data)

        except Exception as e:
            messages.error(request, f"Compression failed: {str(e)}")
            ActivityLog.objects.create(
                user=request.user,
                activity_type='ERROR',
                ip_address=ip_address,
                details=f"Compression failed: {str(e)}"
            )
            return JsonResponse({"success": False, "error": str(e)})

    return render(request, "compress.html")

@login_required
def LogDownloadView(request):
    if request.method == "POST":
        compressed_url = request.POST.get("compressed_url")
        original_size = request.POST.get("original_size")
        compressed_size = request.POST.get("compressed_size")
        ip_address = get_client_ip(request)

        # Log the download action
        ActivityLog.objects.create(
            user=request.user,
            activity_type='DOWNLOAD',
            ip_address=ip_address,
            details=f"User downloaded compressed image from {compressed_url} (Original: {original_size} KB, Compressed: {compressed_size} KB)"
        )

        return JsonResponse({"success": True})

    return JsonResponse({"success": False, "error": "Invalid request method"})

def compress_image_with_jpeg(image_file, quality=85):
    """
    Compress the image using optimized JPEG compression without AI.
    """
    # Load and preprocess the image
    image = Image.open(image_file).convert("RGB")
    original_array = np.array(image)

    # Resize if necessary (optional, keeps image within reasonable dimensions)
    max_size = (1024, 1024)  # Example max resolution
    image.thumbnail(max_size, Image.Resampling.LANCZOS)

    # Save with JPEG compression
    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    unique_filename = f"temp/compressed_{uuid.uuid4().hex}.jpg"
    compressed_path = os.path.join(settings.MEDIA_ROOT, unique_filename)
    
    # Save to a BytesIO object first to optimize quality
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    buffer.seek(0)
    
    # Save to file
    with open(compressed_path, 'wb') as f:
        f.write(buffer.read())
    
    print(f"Saving compressed image to: {compressed_path}")
    print(f"File exists after saving: {os.path.exists(compressed_path)}")

    compressed_image = Image.open(compressed_path)
    compressed_array = np.array(compressed_image)

    return original_array, compressed_array, unique_filename

# def compress_image_with_jpeg(image_file, n_components=100):
#     # Load and preprocess the image from the uploaded file
#     image = Image.open(image_file).convert("RGB")
#     image_array = np.array(image)

#     # Split the image into R, G, and B channels
#     r, g, b = image_array[:, :, 0], image_array[:, :, 1], image_array[:, :, 2]

#     # Apply PCA to each channel
#     def apply_pca(channel):
#         pca = PCA(n_components=n_components)
#         compressed = pca.fit_transform(channel)
#         reconstructed = pca.inverse_transform(compressed)
#         return reconstructed

#     r_compressed = apply_pca(r)
#     g_compressed = apply_pca(g)
#     b_compressed = apply_pca(b)

#     # Stack the channels back together
#     compressed_image = np.stack((r_compressed, g_compressed, b_compressed), axis=2)
#     compressed_image = np.clip(compressed_image, 0, 255).astype(np.uint8)

#     # Convert back to PIL Image
#     compressed_image_pil = Image.fromarray(compressed_image)

#     # Ensure the 'temp' directory exists in MEDIA_ROOT
#     temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
#     if not os.path.exists(temp_dir):
#         os.makedirs(temp_dir)

#     # Save the compressed image to a unique temporary file
#     unique_filename = f"temp/compressed_{uuid.uuid4().hex}.jpg"
#     compressed_path = os.path.join(settings.MEDIA_ROOT, unique_filename)
#     print(f"Saving compressed image to: {compressed_path}")  # Debug print
#     compressed_image_pil.save(compressed_path, 'JPEG')
#     print(f"File exists after saving: {os.path.exists(compressed_path)}")  # Debug print

#     # Return relative path for storage and URL generation
#     return image_array, compressed_image, unique_filename

def ContactView(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')
        ip_address = get_client_ip(request)
        
        Contact.objects.create(
            name=name,
            email=email,
            message=message,
            ip_address=ip_address
        )
        
        ActivityLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            activity_type='CONTACT',
            ip_address=ip_address,
            details=f"Contact form submitted by {name} ({email})"
        )
        
        email_body = f"""
        New Contact Form Submission:
        
        Name: {name}
        Email: {email}
        Message: {message}
        IP Address: {ip_address}
        """
        
        email = EmailMessage(
            'New Contact Form Submission',
            email_body,
            settings.EMAIL_HOST_USER,
            [settings.EMAIL_HOST_USER],
            reply_to=[email],
        )
        email.send()
        
        messages.success(request, "Thank you for your message. We'll get back to you soon!")
        return redirect('contact')
    
    return render(request, 'contact.html')

@login_required
def UserProfileView(request):
    return render(request, 'profile.html')

@login_required
def UpdateProfileView(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        ip_address = get_client_ip(request)
        
        if User.objects.filter(username=username).exclude(id=request.user.id).exists():
            messages.error(request, "Username already exists!")
            return redirect('profile')
        
        user = request.user
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.save()
        
        ActivityLog.objects.create(
            user=user,
            activity_type='PAGE_VIEW',
            ip_address=ip_address,
            details="User updated profile"
        )
        
        messages.success(request, "Profile updated successfully!")
        return redirect('profile')
    
    return redirect('profile')

def AboutView(request):
    return render(request, 'about.html')

# Views for image generation
HUGGINGFACE_API_TOKEN = getattr(settings, 'HUGGINGFACE_API_TOKEN', None)
MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
HEADERS = {"Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}"}

@login_required
def generate_image(request):
    if request.method == 'POST':
        prompt = request.POST.get('prompt')
        if not prompt:
            return render(request, 'generate_image.html', {'error': 'Please enter a prompt.'})

        if not HUGGINGFACE_API_TOKEN:
            return render(request, 'generate_image.html', {'error': 'Hugging Face API token is not configured in settings.'})

        payload = {"inputs": prompt}
        try:
            response = requests.post(API_URL, headers=HEADERS, json=payload)
            response.raise_for_status()
            image_bytes = response.content
            print(f"Received image bytes: {len(image_bytes)} bytes")

            img = Image.open(io.BytesIO(image_bytes))
            print(f"Opened image mode: {img.mode}")

            if img.mode != 'RGB':
                img = img.convert('RGB')
                print("Converted to RGB")

            output = io.BytesIO()
            img.save(output, format='JPEG', quality=90)
            output.seek(0)
            image_bytes_jpg = output.read()
            print(f"JPG image bytes: {len(image_bytes_jpg)} bytes")

            image_file = ContentFile(image_bytes_jpg, name=f"generated_image_{prompt[:20]}.jpg")
            # filename = default_storage.save('generated_images', image_file)
            # image_url = default_storage.url(filename)
            filename = f"generated_images/generated_image_{prompt[:20].replace(' ', '_')}.jpg"
            image_file = ContentFile(image_bytes_jpg)
            saved_path = default_storage.save(filename, image_file)
            image_url = default_storage.url(saved_path)

            print(f"Saved image URL: {image_url}")

            return render(request, 'generate_image.html', {'image_url': image_url})

        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            return render(request, 'generate_image.html', {'error': f'API request failed: {e}'})
        except Exception as e:
            print(f"Error processing image: {e}")
            return render(request, 'generate_image.html', {'error': f'Error processing image: {e}'})
    else:
        return render(request, 'generate_image.html')