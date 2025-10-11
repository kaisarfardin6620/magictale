from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from .serializers import AdminChangePasswordSerializer, AdminProfileUpdateSerializer

def change_admin_password(user, data, context):
    serializer = AdminChangePasswordSerializer(data=data, context=context)
    serializer.is_valid(raise_exception=True)
    user.set_password(serializer.validated_data['new_password'])
    user.save()
    
    OutstandingToken.objects.filter(user=user).delete()
    
    return user


def update_admin_profile(user, data, context):
    serializer = AdminProfileUpdateSerializer(instance=user, data=data, context=context, partial=True)
    
    serializer.is_valid(raise_exception=True)
    serializer.save()
    
    return user