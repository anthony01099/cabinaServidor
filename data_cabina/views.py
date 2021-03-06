import json, io
from django.http import Http404, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, permissions, status
from rest_framework.pagination import PageNumberPagination
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from api_cabina.permissions import IsSuperUser
from auth_cabina.models import UserToken
from .serializers import *
from .models import *
from .utils import get_comapany_tokens, send_notification_to_token_list


class CompanyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows cabin companies to be seen.
    """
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperUser]


class CompanyAbstractView(APIView):
    """
        Abstract view for retrieving company data
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination

    def __init__(self, *args, **kwargs):
        super(CompanyAbstractView, self).__init__(*args, **kwargs)
        self.company = None

    def check(self, request):
        try:
            self.company = request.user.client.company
        except:
            return Response({'detail': 'No companies related to current user.'})

    @property
    def paginator(self):
        """
        The paginator instance associated with the view, or `None`.
        """
        if not hasattr(self, '_paginator'):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = self.pagination_class()
        return self._paginator

    def paginate_queryset(self, queryset):
        """
        Return a single page of results, or `None` if pagination is disabled.
        """
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        """
        Return a paginated style `Response` object for the given output data.
        """
        assert self.paginator is not None
        return self.paginator.get_paginated_response(data)


class CompanyData(CompanyAbstractView):
    """
        Returns data for the user's company
    """

    def get(self, request):
        result = self.check(request)
        if self.company:
            serializer = CompanySerializer(self.company)
            return Response(serializer.data)
        return result


class CompanyCabins(CompanyAbstractView):
    """
        Returns cabins for a particular company
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        result = self.check(request)
        if self.company:
            cabins = Cabin.objects.filter(company=self.company)
            cabins = self.paginate_queryset(cabins)
            serializer = CompanyCabinSerializer(cabins, many=True)
            return self.get_paginated_response(serializer.data)
        return result


class CompanyCaptures(CompanyAbstractView):
    """
        Returns captures for a particular company
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        result = self.check(request)
        if self.company:
            captures = Capture.objects.filter(cabin__company=self.company).order_by('-created_at')
            captures = self.paginate_queryset(captures)
            serializer = SimpleCaptureSerializer(captures, many=True)
            return self.get_paginated_response(serializer.data)
        return result


class CompanyCaptureImage(CompanyAbstractView):
    """
        Returns capture image for a particular capture id
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, capture_id):
        result = self.check(request)
        if self.company:
            try:
                capture = Capture.objects.get(id=capture_id)
            except:
                return Response({'detail': 'Invalid capture id'})
            else:
                serializer = CaptureImageSerializer(capture)
                return Response(serializer.data)
        return result


class RetrieveCompanyCapture(CompanyAbstractView):
    """
        Returns capture for a particular company
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, capture_id):
        result = self.check(request)
        if self.company:
            try:
                capture = Capture.objects.get(id=capture_id, cabin__company=self.company)
            except:
                return Response({"detail": "Capture id not valid."})
            else:
                serializer = CaptureSerializer(capture)
                return Response(serializer.data)
        return result


class CabinCaptures(CompanyAbstractView):
    """
        Returns captures for a particular cabin
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, cabin_id):
        result = self.check(request)
        if self.company:
            cabin = Cabin.objects.filter(id=cabin_id)

            if not cabin.exists():
                return Response({"detail": "You do not have access to this"})

            if self.company != cabin.first().company:
                return Response({"detail": "You do not have access to this"})

            captures = Capture.objects.filter(cabin__id=cabin_id).order_by('-created_at')
            captures = self.paginate_queryset(captures)
            serializer = SimpleCaptureSerializer(captures, many=True)
            return self.get_paginated_response(serializer.data)
        return result


class CaptureViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows cabin captures to be seen.
    """
    queryset = Capture.objects.all().order_by('-created_at')
    serializer_class = SimpleCaptureSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperUser]


@method_decorator(csrf_exempt, name='dispatch')
class CreateCapture(View):
    """
        Create a capture with a post request.
    """

    def get(self, request):
        return JsonResponse({'detail': 'Error. Must use post to create a capture'})

    def post(self, request):
        data = json.loads(request.body)
        # Get cabin instance
        try:
            cabin = Cabin.objects.get(token__id=data['token'])
        except:
            return JsonResponse({'detail': 'failed, invalid token'})
        else:
            company = cabin.company
            db_settings = Setting.objects.filter(company=company)
            is_image_saved = True if len(db_settings) == 0 else db_settings.latest('created_at').save_all
            # Create capture object
            capture = Capture(cabin=cabin,
                              temp=data['temp'],
                              is_wearing_mask=data['is_wearing_mask'],
                              is_image_saved=is_image_saved)
            capture.save()
            # Create image file
            if is_image_saved:
                image_bytes = io.BytesIO()
                image_bytes.write(data['image_base64'].encode())
                capture.image.save(str(capture.id) + '.txt', image_bytes)

            # Send alert to users
            is_alert = (float(data['temp']) >= settings.ALERT_TEMPERATURE) or (not data['is_wearing_mask'])
            if is_alert:
                msg = {
                    'type': 'cabin_alert',
                    'capture_id': capture.id,
                    'temp': data['temp'],
                    'is_wearing_mask': is_image_saved,
                }
                alert = 'Person with temp: ' + str(data['temp'])
                tokens_to_send_notification = get_comapany_tokens(cabin.company)
                send_notification_to_token_list(tokens_to_send_notification, msg)
                try:
                    channel_layer = get_channel_layer()
                except:
                    pass
                else:
                    async_to_sync(channel_layer.group_send)(str(cabin.company.id), msg)
        return JsonResponse({'detail': 'successful'})


class CabinInfo(View):
    def get(self, request):
        token = request.GET.get("token")
        if token is None:
            return JsonResponse({'detail': 'failed, invalid token'})

        cabin_obj = Cabin.objects.filter(token=token)
        if not cabin_obj.exists():
            return JsonResponse({'detail': 'failed, invalid token'})

        cabin_obj = cabin_obj.first()
        ssid = cabin_obj.wifi_ssid
        password = cabin_obj.wifi_password
        language = cabin_obj.language
        return JsonResponse({'ssid': ssid, 'password': password, 'language': language,})


class RegisterCabin(CompanyAbstractView):
    """
        Register a cabin using a token.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({'detail': 'Error. Must use post to register a cabin'})

    def post(self, request):
        # Retrieve data
        result = self.check(request)
        if self.company:
            token_str = request.data['token']
            try:
                token = CabinToken.objects.get(id=token_str)
            except:
                return Response({'detail': 'Token not valid'})
            else:
                if token.is_used:
                    return Response({'detail': 'Token already used'})
                else:
                    cabin = Cabin(company=self.company, token=token)
                    cabin.save()
                    token.is_used = True
                    token.save()
                    return Response({'detail': 'successful', 'cabin_id': cabin.id})
        return result


class AssociateUserToken(CompanyAbstractView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            token = request.data["token"]
            token_obj = UserToken()
            token_obj.token = token
            token_obj.user = request.user
            token_obj.save()
            return JsonResponse({'detail': 'successful'}, status=status.HTTP_201_CREATED)
        except:
            return JsonResponse({'error': "Error while saving token"}, status=status.HTTP_400_BAD_REQUEST)


class RemoveUserToken(CompanyAbstractView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:

            token = request.data["token"]
            token_obj = UserToken.objects.get(token=token)

            if request.user != token_obj.user:
                return JsonResponse({'detail': "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

            token_obj.delete()
            return JsonResponse({'detail': 'successful'}, status=status.HTTP_200_OK)
        except:
            return JsonResponse({'detail': "Error while unsubscribing"}, status=status.HTTP_400_BAD_REQUEST)


class BoothControlView(APIView):
    """
        Abstract view for retrieving company dat
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        booth_id = request.data['booth_id']
        #Check if token is valid for a booth
        try:
            booth = Cabin.objects.get(id=booth_id)
            booth_token = booth.token.id
        except:
            return Response({'detail': "invalid booth id"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if booth.company.id != request.user.client.company.id:
                return Response({'detail': "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        #Check if the booth belongs to the logged user
        if booth.company.id != request.user.client.company.id:
            return Response({'detail': "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        #Send data
        msg = {
                'type': 'booth_info',
                'operation': request.data['operation'],
                'is_booth_on': request.data['is_booth_on'],
                'is_autocleaning': request.data['is_autocleaning'],
        }
        try:
                channel_layer = get_channel_layer()
        except:
            pass
        else:
            try:
                async_to_sync(channel_layer.group_send)(booth_token, msg)
            except:
                return Response({'detail': 'error sending data'})
            else:
                return Response({'detail': 'successful'})
