from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, permissions
from .models import User, Word, ApprovalWorkflow, Contribution, PointsSystem
from .serializers import UserSerializer, WordSerializer, ApprovalWorkflowSerializer, ContributionSerializer, PointsSystemSerializer
from .utils import search_word_in_pdfs, generate_definition
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

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
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
class WordViewSet(viewsets.ModelViewSet):
    queryset = Word.objects.all()
    serializer_class = WordSerializer
    permission_classes = [AllowAny]  

    def perform_create(self, serializer):
        created_by_id = self.request.data.get('created_by')

        if created_by_id:
            user = User.objects.get(id=created_by_id)
            serializer.save(created_by=user)
            instance = serializer.save()
            Contribution.objects.create(user=user, word=instance, action='add')
            PointsSystem.objects.filter(user=user).update(points=F('points') + 5)
        else:
            instance = serializer.save()
    
    @action(detail=True, methods=['post'], permission_classes=[AllowAny])  # Remplacé IsModeratorOrAdmin
    def change_status(self, request, pk=None):
        """Allow anyone to approve or reject words."""
        word = self.get_object()
        new_status = request.data.get('status')
        comment = request.data.get('comment', '')

        if new_status not in ['review', 'approved']:
            return Response({'error': 'Invalid status'}, status=400)

        # Approve the word
        word.status = new_status
        word.moderator_comment = comment
        word.save()

        # Award points only if the creator is authenticated
        if word.created_by:
            PointsSystem.objects.filter(user=word.created_by).update(points=F('points') + 10)

        return Response({'message': f'Word status updated to {new_status}'})

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])  # Remplacé IsAuthenticated
    def history(self, request, pk=None):
        """Récupère l'historique des changements de statut d'un mot."""
        word = self.get_object()
        history = word.history.all().values('previous_status', 'new_status', 'changed_by__username', 'changed_at', 'comment')
        return Response(list(history))


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

    # ✅ Ensure users with no points still appear (use Coalesce to replace None with 0)
    users_with_points = User.objects.annotate(
        total_points=Coalesce(Sum('pointssystem__points'), Value(0))  # ✅ Fix None issue
    ).order_by('-total_points')

    leaderboard_data = []
    rank = 0
    previous_points = None

    for index, user in enumerate(users_with_points):
        user_points = user.total_points  # ✅ Guaranteed to be at least 0 now
        
        # ✅ Only increase rank if points change
        if previous_points is None or user_points < previous_points:
            rank = index + 1  # ✅ Rank increases only when points decrease
        
        previous_points = user_points  # ✅ Store points for next loop iteration

        leaderboard_data.append({
            "rank": rank,
            "username": user.username,
            "points": user_points
        })

    return Response(leaderboard_data)
