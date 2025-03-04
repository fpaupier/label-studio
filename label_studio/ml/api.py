"""This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license.
"""
import logging
import drf_yasg.openapi as openapi
from drf_yasg.utils import swagger_auto_schema
from django.utils.decorators import method_decorator
from django.conf import settings

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView
from rest_framework.response import Response

from core.permissions import all_permissions
from core.utils.common import get_object_with_check_and_log
from projects.models import Project, Task
from ml.serializers import MLBackendSerializer, MLInteractiveAnnotatingRequest
from ml.models import MLBackend
from ml.api_connector import MLApi
from core.utils.common import bool_from_request

logger = logging.getLogger(__name__)


@method_decorator(
    name='post',
    decorator=swagger_auto_schema(
        tags=['Machine Learning'],
        operation_summary='Add ML Backend',
        operation_description="""
    Add an ML backend to a project using the Label Studio UI or by sending a POST request using the following cURL 
    command:
    ```bash
    curl -X POST -H 'Content-type: application/json' {host}/api/ml -H 'Authorization: Token abc123'\\
    --data '{{"url": "http://localhost:9090", "project": {{project_id}}}}' 
    """.format(
            host=(settings.HOSTNAME or 'https://localhost:8080')
        ),
    ),
)
@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Machine Learning'],
        operation_summary='List ML backends',
        operation_description="""
    List all configured ML backends for a specific project by ID.
    Use the following cURL command:
    ```bash
    curl {host}/api/ml?project={{project_id}} -H 'Authorization: Token abc123'
    """.format(
            host=(settings.HOSTNAME or 'https://localhost:8080')
        ),
    ))
class MLBackendListAPI(generics.ListCreateAPIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)
    permission_required = all_permissions.projects_change
    serializer_class = MLBackendSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["is_interactive"]

    def get_queryset(self):
        project_pk = self.request.query_params.get('project')
        project = get_object_with_check_and_log(self.request, Project, pk=project_pk)
        self.check_object_permissions(self.request, project)
        ml_backends = MLBackend.objects.filter(project_id=project.id)
        for mlb in ml_backends:
            mlb.update_state()
        return ml_backends

    def perform_create(self, serializer):
        ml_backend = serializer.save()
        ml_backend.update_state()


@method_decorator(
    name='patch',
    decorator=swagger_auto_schema(
        tags=['Machine Learning'],
        operation_summary='Update ML Backend',
        operation_description="""
    Update ML backend parameters using the Label Studio UI or by sending a PATCH request using the following cURL command:
    ```bash
    curl -X PATCH -H 'Content-type: application/json' {host}/api/ml/{{ml_backend_ID}} -H 'Authorization: Token abc123'\\
    --data '{{"url": "http://localhost:9091"}}' 
    """.format(
            host=(settings.HOSTNAME or 'https://localhost:8080')
        ),
    ),
)
@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Machine Learning'],
        operation_summary='Get ML Backend',
        operation_description="""
    Get details about a specific ML backend connection by ID. For example, make a GET request using the
    following cURL command:
    ```bash
    curl {host}/api/ml/{{ml_backend_ID}} -H 'Authorization: Token abc123'
    """.format(
            host=(settings.HOSTNAME or 'https://localhost:8080')
        ),
    ),
)
@method_decorator(
    name='delete',
    decorator=swagger_auto_schema(
        tags=['Machine Learning'],
        operation_summary='Remove ML Backend',
        operation_description="""
    Remove an existing ML backend connection by ID. For example, use the
    following cURL command:
    ```bash
    curl -X DELETE {host}/api/ml/{{ml_backend_ID}} -H 'Authorization: Token abc123'
    """.format(
            host=(settings.HOSTNAME or 'https://localhost:8080')
        ),
    ),
)
@method_decorator(name='put', decorator=swagger_auto_schema(auto_schema=None))
class MLBackendDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)
    serializer_class = MLBackendSerializer
    permission_required = all_permissions.projects_change
    queryset = MLBackend.objects.all()

    def get_object(self):
        ml_backend = super(MLBackendDetailAPI, self).get_object()
        ml_backend.update_state()
        return ml_backend

    def perform_update(self, serializer):
        ml_backend = serializer.save()
        ml_backend.update_state()


@method_decorator(
    name='post',
    decorator=swagger_auto_schema(
        tags=['Machine Learning'],
        operation_summary='Train',
        operation_description="""
        After you add an ML backend, call this API with the ML backend ID to start training with 
        already-labeled tasks. 
        
        Get the ML backend ID by [listing the ML backends for a project](https://labelstud.io/api/#operation/api_ml_list).
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'use_ground_truth': openapi.Schema(
                    type=openapi.TYPE_BOOLEAN, description='Whether to include ground truth annotations in training'
                )
            },
        ),
        responses={
            200: openapi.Response(title='Training OK', description='Training has successfully started.'),
            500: openapi.Response(
                description='Training error',
                schema=openapi.Schema(
                    title='Error message',
                    description='Error message',
                    type=openapi.TYPE_STRING,
                    example='Server responded with an error.',
                ),
            ),
        },
    ),
)
class MLBackendTrainAPI(APIView):

    permission_required = all_permissions.projects_change

    def post(self, request, *args, **kwargs):
        ml_backend = get_object_with_check_and_log(request, MLBackend, pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, ml_backend)

        ml_backend.train()
        return Response(status=status.HTTP_200_OK)


@method_decorator(
    name='post',
    decorator=swagger_auto_schema(
        tags=['Machine Learning'],
        operation_summary='Request Interactive Annotation',
        operation_description="""
        Send a request to the machine learning backend set up to be used for interactive preannotations to retrieve a
        predicted region based on annotator input. 
        See [set up machine learning](ml.html#Get-interactive-preannotations) for more.
        """,
        request_body=MLInteractiveAnnotatingRequest,
        responses={
            200: openapi.Response(title='Annotating OK', description='Interactive annotation has succeeded.'),
        },
    ),
)
class MLBackendInteractiveAnnotating(APIView):
    def post(self, request, *args, **kwargs):
        ml_backend = get_object_with_check_and_log(request, MLBackend, pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, ml_backend)
        serializer = MLInteractiveAnnotatingRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        task = get_object_with_check_and_log(request, Task, pk=validated_data['task'], project=ml_backend.project)
        context = validated_data.get('context')

        result = ml_backend.interactive_annotating(task, context)

        return Response(
            result,
            status=status.HTTP_200_OK,
        )
