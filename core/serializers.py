from rest_framework import serializers
from .models import User, Word, ApprovalWorkflow, Contribution, PointsSystem

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
    class Meta:
        model = Word
        fields = ['id', 'text', 'definition', 'status', 'created_at', 'moderator_comment','created_by']
        read_only_fields = ['status', 'created_at', 'created_by']  # Ensure `created_by` is not required in input

    def create(self, validated_data):
        request = self.context.get('request')  # Get request context
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)
class ApprovalWorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalWorkflow
        fields = '__all__'

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
