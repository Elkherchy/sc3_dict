from rest_framework import serializers
from .models import User, Word, ApprovalWorkflow, Contribution, PointsSystem , ModeratorComment

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'role','email','created_at']
    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data["username"],
            email=validated_data["email"],
            role=validated_data.get("role", "contributor")
        )
        user.set_password(validated_data["password"])
        user.save()
        return user
class WordSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', read_only=True)  # Ajout du username

    class Meta:
        model = Word
        fields = ['id', 'text', 'definition', 'status', 'created_at', 'examples', 'created_by','likes','types']
        read_only_fields = ['status', 'created_at', 'created_by']  

    def create(self, validated_data):        
        return super().create(validated_data)
class ApprovalWorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalWorkflow
        fields = '__all__'

class ModeratorCommentSerializer(serializers.ModelSerializer):
    moderator = serializers.CharField(source='moderator.username', read_only=True)  # Récupère username du modérateur
    word = serializers.CharField(source='word.text', read_only=True)  # Récupère le texte du mot
    moderator_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source='moderator', write_only=True)
    word_id = serializers.PrimaryKeyRelatedField(queryset=Word.objects.all(), source='word', write_only=True)

    class Meta:
        model = ModeratorComment
        fields = ['id', 'comment', 'created_at', 'word', 'moderator', 'moderator_id', 'word_id']  # Ajout de moderator_id et word_id

class ContributionSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField() 
    word = serializers.SerializerMethodField() 
    class Meta:
        model = Contribution
        fields = ['id', 'action', 'timestamp', 'user', 'word']

    def get_user(self, obj):
        return obj.user.username if obj.user else None  
    def get_word(self, obj):
        return obj.word.text if obj.word else None  
class PointsSystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointsSystem
        fields = '__all__'
