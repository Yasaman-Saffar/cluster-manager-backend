from kubernetes import client

def get_kubernetes_client(cluster):
    configuration = client.Configuration()

    configuration.host = f"https://{cluster.address}"
    configuration.verify_ssl = False

    configuration.api_key["BearerToken"] = cluster.token
    configuration.api_key_prefix["BearerToken"] = "Bearer"

    return client.ApiClient(configuration)