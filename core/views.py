from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, permissions
from .models import User, Word, ApprovalWorkflow, Contribution, PointsSystem,ModeratorComment
from .serializers import UserSerializer, WordSerializer,ModeratorCommentSerializer, ApprovalWorkflowSerializer, ContributionSerializer, PointsSystemSerializer
from .utils import generate_variants, search_word_in_pdfs, generate_definition
import json
from core.models import WordHistory  # Assure-toi que le modèle est bien importé
from django.db.models import F
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from core.models import PointsSystem
from django.contrib.auth import get_user_model
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType  # ✅ Import this!
from django.db.models.functions import Coalesce
from django.db.models import Sum , F, Value
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .models import UploadedDocument
from .serializers import UploadedDocumentSerializer
from django.shortcuts import get_object_or_404

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

class ModeratorCommentViewSet(viewsets.ModelViewSet):
    queryset = ModeratorComment.objects.all()
    serializer_class = ModeratorCommentSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        """Permet de filtrer les commentaires par mot s'il y a un paramètre 'word_id' dans la requête."""
        queryset = super().get_queryset()
        word_id = self.request.query_params.get('word_id')
        if word_id:
            queryset = queryset.filter(word_id=word_id)
        return queryset 
    
class IsModeratorOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['moderator', 'admin']

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({
                'error': 'Username and password are required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        print(f"Received credentials: username={username}, password={password}")

        user = authenticate(username=username, password=password)
        
        if user is not None:
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token

            return Response({

                'refresh': str(refresh),
                'access': str(access_token),
                'id':user.id,
                'username': user.username,
                'role': user.role,
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Invalid credentials'
                
            }, status=status.HTTP_401_UNAUTHORIZED)
class RegisterUserView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            # Ensure groups exist
            admin_group, _ = Group.objects.get_or_create(name='Admin')
            moderator_group, _ = Group.objects.get_or_create(name='Moderator')
            contributor_group, _ = Group.objects.get_or_create(name='Contributor')

            # Ensure permissions exist with correct content type
            user_content_type = ContentType.objects.get_for_model(User)
            
            permission_view_users, _ = Permission.objects.get_or_create(
                codename='can_view_users',
                name='Can view users',
                content_type=user_content_type
            )
            permission_edit_users, _ = Permission.objects.get_or_create(
                codename='can_edit_users',
                name='Can edit users',
                content_type=user_content_type
            )

            # Assign permissions to groups
            admin_group.permissions.add(permission_view_users, permission_edit_users)
            moderator_group.permissions.add(permission_view_users)
            contributor_group.permissions.add(permission_view_users)

            # Register user
            serializer = UserSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.save()
                user.set_password(serializer.validated_data["password"])
                user.save()

                # Assign user to role-based group
                role = user.role.lower()
                if role == 'admin':
                    user.groups.add(admin_group)
                elif role == 'moderator':
                    user.groups.add(moderator_group)
                elif role == 'contributor':
                    user.groups.add(contributor_group)

                return Response({
                    "message": "User created and groups, permissions assigned successfully"
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    "error": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
GROQ_API_KEY = "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"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
class WordViewSet(viewsets.ModelViewSet):
    queryset = Word.objects.all()
    serializer_class = WordSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        created_by_id = self.request.data.get('created_by')

        if created_by_id:
            try:
                user = User.objects.get(id=created_by_id)
                instance = serializer.save(created_by=user)
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        elif self.request.user.is_authenticated:
            instance = serializer.save(created_by=self.request.user)
            user = self.request.user
        else:
            instance = serializer.save()
            return

        # ✅ Log the contribution
        Contribution.objects.create(user=user, word=instance, action='add')

        # ✅ Ensure user has a PointsSystem entry
        points_entry, created = PointsSystem.objects.get_or_create(user=user, defaults={"points": 0})

        # ✅ Add 5 points for adding a word
        points_entry.points = F('points') + 5
        points_entry.save()

        # ✅ Generate AI variants
        ai_variants = generate_variants(instance.text)
        instance.variants = ai_variants
        instance.save()
        
        return instance
    
    @action(detail=True, methods=['post'], permission_classes=[AllowAny])  # Remplacé IsModeratorOrAdmin
    def change_status(self, request, pk=None):
        """Allow anyone to approve or reject words."""
        word = self.get_object()
        new_status = request.data.get('status')

        if new_status not in ['review', 'approved']:
            return Response({'error': 'Invalid status'}, status=400)

        # Approve the word
        word.status = new_status
        word.save()

        # Award points only if the creator is authenticated
        if word.created_by:
            points_entry, _ = PointsSystem.objects.get_or_create(user=word.created_by, defaults={"points": 0})
            points_entry.points = F('points') + 10
            points_entry.save()

        return Response({'message': f'Word status updated to {new_status}'})
    @action(detail=True, methods=['post'])
    def regenerate_variants(self, request, pk=None):
        """Re-generates AI variants for the word in the text field."""
        word = self.get_object()
        word.variants = generate_variants(word.text)  # ✅ Use text field for AI generation
        word.save()
        return Response({"message": "Variants regenerated", "variants": word.variants})
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])  # Remplacé IsAuthenticated
    def history(self, request, pk=None):
        """Récupère l'historique des changements de statut d'un mot."""
        word = self.get_object()
        history = word.history.all().values('previous_status', 'new_status', 'changed_by__username', 'changed_at', 'comment')
        return Response(list(history))
    @action(detail=True, methods=['post'], permission_classes=[AllowAny])
    def like(self, request, pk=None):
        """Incrémente le nombre de likes d'un mot."""
        word = self.get_object()
        word.likes = F('likes') + 1
        word.save()
        word.refresh_from_db()
        return Response({'message': 'Like added', 'likes': word.likes})

class ApprovalWorkflowViewSet(viewsets.ModelViewSet):
    queryset = ApprovalWorkflow.objects.all()
    serializer_class = ApprovalWorkflowSerializer
    permission_classes = [AllowAny]  # Remplacé IsAuthenticated par AllowAny


class ContributionViewSet(viewsets.ModelViewSet):
    queryset = Contribution.objects.all()
    serializer_class = ContributionSerializer
    permission_classes = [AllowAny]  # Remplacé IsAuthenticated par AllowAny

    @action(detail=True, methods=['post'], permission_classes=[AllowAny])  # Remplacé IsModeratorOrAdmin
    def add_comment(self, request, pk=None):
        contribution = self.get_object()
        comment = request.data.get('comment', '').strip()
        if not comment:
            return Response({'error': 'Comment cannot be empty'}, status=400)
        contribution.comment = comment
        contribution.save()
        return Response({'message': 'Comment added successfully'})


class PointsSystemViewSet(viewsets.ModelViewSet):
    queryset = PointsSystem.objects.all()
    serializer_class = PointsSystemSerializer
    permission_classes = [AllowAny]  # Remplacé IsAuthenticated par AllowAny
    @action(detail=True, methods=['post'])
    def add_points(self, request, pk=None):
        """Add points to a user. If no entry exists, create one."""
        points_to_add = request.data.get('points', 0)

        # ✅ Validate points input
        if not isinstance(points_to_add, int) or points_to_add < 0:
            return Response({"error": "Invalid points amount"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Ensure user exists
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # ✅ Create PointsSystem entry if missing
        points_entry, created = PointsSystem.objects.get_or_create(user=user)

        # ✅ Update points
        points_entry.points = F('points') + points_to_add
        points_entry.save()

        return Response({"message": f"{points_to_add} points added successfully!"})
@csrf_exempt
def chatbot_query(request):
    """
    Handles natural language queries about Hassaniya words.
    - **First**, searches for the word in PDFs.
    - **If not found**, asks Groq AI to generate a definition.
    - **If AI also doesn't know**, asks the user to provide a definition.
    """
    if request.method == "POST":
        data = json.loads(request.body)
        user_input = data.get("query", "").strip()

        if not user_input:
            return JsonResponse({"error": "Aucune requête fournie"}, status=400)

        # ✅ Search in PDFs first
        pdf_result = search_word_in_pdfs(user_input)
        if pdf_result:
            return JsonResponse(pdf_result)

        # ✅ If not found, ask AI for a definition in **French**
        ai_response = generate_definition(user_input)

        if "Je ne connais pas ce mot" in ai_response:
            return JsonResponse({
                "response": f"Je ne connais pas ce mot. Pouvez-vous m'expliquer '{user_input}' ? J'apprendrai de votre réponse."
            })

        return JsonResponse({"word": user_input, "definition": ai_response})

    return JsonResponse({"error": "Requête invalide"}, status=400)

User = get_user_model()

@api_view(['GET'])
@permission_classes([AllowAny])  # Déjà configuré avec AllowAny
def leaderboard(request):
    """Returns a public leaderboard sorted by points (descending) with correct ranking."""

    users_with_points = User.objects.annotate(
        total_points=Coalesce(Sum('pointssystem__points'), Value(0))
    ).order_by('-total_points')

    leaderboard_data = []
    rank = 0
    previous_points = None

    for index, user in enumerate(users_with_points):
        user_points = user.total_points
        
        # ✅ Only increase rank if points change
        if previous_points is None or user_points < previous_points:
            rank = index + 1 
        
        previous_points = user_points

        leaderboard_data.append({
            "rank": rank,
            "username": user.username,
            "points": user_points
        })

    return Response(leaderboard_data)


class FileUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [permissions.AllowAny]  # ✅ No authentication required

    def post(self, request, *args, **kwargs):
        user_id = request.data.get("user_id")  # ✅ Get user_id from request

        if not user_id:
            return Response({"error": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(User, id=user_id)  # ✅ Validate user ID

        file_serializer = UploadedDocumentSerializer(data=request.data)
        if file_serializer.is_valid():
            file_serializer.save(uploaded_by=user)  # ✅ Save with user ID instead of token
            points_entry, created = PointsSystem.objects.get_or_create(user=user, defaults={"points": 0})
            points_entry.points = F('points') + 5
            points_entry.save()
            return Response(file_serializer.data, status=status.HTTP_201_CREATED)


        else:
            return Response(file_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    @action(detail=True, methods=['post'], permission_classes=[AllowAny])  # Remplacé IsModeratorOrAdmin
    def change_status(self, request, pk=None):
        """Allow anyone to approve or reject words."""
        file = self.get_object()
        new_status = request.data.get('status')

        if new_status not in ['review', 'approved']:
            return Response({'error': 'Invalid status'}, status=400)

        # Approve the word
        file.status = new_status
        file.save()

        # Award points only if the creator is authenticated
        if file.user_id:
            points_entry, _ = PointsSystem.objects.get_or_create(user=file.user_id, defaults={"points": 0})
            points_entry.points = F('points') + 10
            points_entry.save()
    def get(self, request, *args, **kwargs):
        """Get all uploaded PDFs."""
        documents = UploadedDocument.objects.all()
        serializer = UploadedDocumentSerializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
def view_pdf(request, file_id):
    document = get_object_or_404(UploadedDocument, id=file_id)
    return FileResponse(document.file.open(), content_type='application/pdf')