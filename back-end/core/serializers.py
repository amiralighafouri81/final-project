from djoser.serializers import UserSerializer as BaseUserSerializer, UserCreateSerializer as BaseUserCreateSerializer
from rest_framework import serializers
from faculty.models import Student
from core.models import User


class UserCreateSerializer(BaseUserCreateSerializer):
    student_number = serializers.CharField(write_only=True, required=False)
    biography = serializers.CharField(write_only=True, required=False, default='')
    password_confirmation = serializers.CharField(write_only=True, style={'input_type': 'password'})
    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'username',
            'student_number', 'biography', 'password', 'password_confirmation'
        ]

    def validate(self, attrs):
        self.student_number = attrs.pop('student_number', None)
        self.biography = attrs.pop('biography', '')
        if attrs['password'] != attrs.pop('password_confirmation'):
            raise serializers.ValidationError({"password_confirmation": "Passwords do not match."})
        return super().validate(attrs)

    def create(self, validated_data):
        user = super().create(validated_data)

        user.role = User.STUDENT  # Set role to 'Student'
        user.save()

        if self.student_number:
            Student.objects.create(
                user=user, 
                student_number=self.student_number,
                biography=self.biography or ''
            )

        return user


class UserCreatePasswordRetypeSerializer(UserCreateSerializer):
    """Serializer for user creation with password retype confirmation."""
    pass


class UserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ['id', 'username', 'first_name', 'last_name']
