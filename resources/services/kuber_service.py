from kubernetes import client, config
from .kubernetes_client import get_kubernetes_client

from resources.models import App

def create_kuber_namespace(cluster, ns_name):

    api_client = get_kubernetes_client(cluster)
    v1 = client.CoreV1Api(api_client)
    namespace = client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name=ns_name
        )
    )

    v1.create_namespace(body=namespace)



def delete_kuber_namespace(cluster, ns_name):
    api_client = get_kubernetes_client(cluster)
    v1 = client.CoreV1Api(api_client)

    v1.delete_namespace(name=ns_name)



def create_app_deployment(app):
    cluster = app.namespace.cluster
    api_client = get_kubernetes_client(cluster)
    apps_v1 = client.AppsV1Api(api_client)

    resources = client.V1ResourceRequirements(
        requests={
            "cpu": app.cpu_request,
            "memory": app.memory_request,
        },
        limits={
            "cpu": app.cpu_limit,
            "memory": app.memory_limit,
        },
    )

    container = client.V1Container(
        name=app.name,
        image=app.image,
        ports=[
            client.V1ContainerPort(
                container_port=app.container_port
            )
        ] if app.container_port else None,
        resources=resources
    )

    labels = {
        "app": app.name
    }

    pod_template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(
            labels=labels
        ),
        spec=client.V1PodSpec(
            containers=[container]
        )
    )

    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(
            name=app.name
        ),
        spec=client.V1DeploymentSpec(
            replicas=app.replicas,
            selector=client.V1LabelSelector(
                match_labels=labels
            ),
            template=pod_template
        )
    )

    apps_v1.create_namespaced_deployment(
        namespace=app.namespace.name,
        body=deployment
    )

def get_app_status(app):
    cluster = app.namespace.cluster
    api_client = get_kubernetes_client(cluster)
    apps_v1 = client.AppsV1Api(api_client)

    deployment = apps_v1.read_namespaced_deployment(
        name=app.name,
        namespace=app.namespace.name
    )

    desired_replicas = deployment.spec.replicas or 0
    ready_replicas = deployment.status.ready_replicas or 0

    app_status = (
        "ready"
        if ready_replicas == desired_replicas
        else "not-ready"
    )

    return {
        "desired_replicas": desired_replicas,
        "ready_replicas": ready_replicas,
        "status": app_status
    }

def update_app_deployment(app, new_data):
    cluster = app.namespace.cluster
    api_client = get_kubernetes_client(cluster)
    apps_v1 = client.AppsV1Api(api_client)

    image = new_data.get("image", app.image)
    replicas = new_data.get("replicas", app.replicas)
    cpu_request = new_data.get("cpu_request", app.cpu_request)
    cpu_limit = new_data.get("cpu_limit", app.cpu_limit)
    memory_request = new_data.get("memory_request", app.memory_request)
    memory_limit = new_data.get("memory_limit", app.memory_limit)

    body = {
        "spec": {
            "replicas": replicas,
            "template": {
                "spec": {
                    "containers":[
                        {
                            "name": app.name,
                            "image": image,
                            "resources": {
                                "requests": {
                                    "cpu": cpu_request,
                                    "memory": memory_request,
                                },
                                "limits": {
                                    "cpu": cpu_limit,
                                    "memory": memory_limit,
                                }
                            }
                        }
                    ]
                }
            }
        }
    }

    apps_v1.patch_namespaced_deployment(
        name=app.name,
        namespace=app.namespace.name,
        body=body
    )

def delete_kuber_app(app):
    cluster = app.namespace.cluster

    api_client = get_kubernetes_client(cluster)
    apps_v1 = client.AppsV1Api(api_client)
    apps_v1.delete_namespaced_deployment(
        name=app.name,
        namespace=app.namespace.name
    )