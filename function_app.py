import logging
import azure.functions as func
from cryptography.fernet import Fernet
import time
import os
import json
import strava
import scrape
import re
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.identity import DefaultAzureCredential

app = func.FunctionApp()

# Load the key from the environment variable
def load_key_from_env():
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        raise ValueError("No encryption key found in environment variables")
    return key.encode()

# Encrypt data
def encrypt_data(data, key):
    fernet = Fernet(key)
    encrypted_data = fernet.encrypt(data.encode())
    return encrypted_data

# Decrypt data
def decrypt_data(encrypted_data, key):
    fernet = Fernet(key)
    decrypted_data = fernet.decrypt(encrypted_data).decode()
    return decrypted_data

# Initialize Azure Blob Storage client with DefaultAzureCredential
def init_blob_service_client(credential):
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    return BlobServiceClient(account_url, credential=credential)

# Load users data from the encrypted JSON file in Azure Blob storage
def load_users(credential, config_file='users.json.enc'):
    key = load_key_from_env()
    blob_service_client = init_blob_service_client(credential)
    container_name = os.getenv("CONTAINER")
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=config_file)

    # Download the blob data
    encrypted_data = blob_client.download_blob().readall()
    decrypted_data = decrypt_data(encrypted_data, key)
    config = json.loads(decrypted_data)
    return config

# Save users data to the encrypted JSON file in Azure Blob storage
def save_users(credential, config, config_file='users.json.enc'):
    key = load_key_from_env()
    blob_service_client = init_blob_service_client(credential)
    container_name = os.getenv("CONTAINER")
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=config_file)

    data = json.dumps(config, indent=4)
    encrypted_data = encrypt_data(data, key)

    # Upload the encrypted data to Azure Blob storage
    blob_client.upload_blob(encrypted_data, overwrite=True)

def clean_up_old_files(credential, container_name = os.getenv('CONTAINER'), days=7):
    """
    Clean up any html files that are older than a specified number of days in an Azure Blob Storage container.
    """
    # Get the storage account URL from environment variables
    account_url = os.getenv('AZURE_STORAGE_ACCOUNT_URL')
    
    # Create a BlobServiceClient
    blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
    
    # Create a ContainerClient
    container_client = blob_service_client.get_container_client(container_name)
    
    # Convert days to seconds
    cutoff_time = time.time() - days * 86400
    
    # List all blobs in the container
    blobs_list = container_client.list_blobs()
    
    for blob in blobs_list:
        # Check if the blob is an HTML file
        if re.search(r'.*\.html$', blob.name):
            # Get the blob properties to check the creation time
            blob_client = container_client.get_blob_client(blob)
            blob_properties = blob_client.get_blob_properties()
            
            # Azure Blob Storage does not directly provide creation time, we use last modified time
            last_modified_time = blob_properties['last_modified'].timestamp()
            
            if last_modified_time < cutoff_time:
                blob_client.delete_blob()
                print(f"Removed old file: {blob.name}")

def main():
    # Authenticate with DefaultAzureCredential
    credential = DefaultAzureCredential()

    # Clean up old files
    clean_up_old_files(credential)

    users = load_users(credential)

    for account in users['accounts']:
        runner_id = account['RUNNER_ID']
        access_token = account['STRAVA_ACCESS_TOKEN']
        refresh_token = account['STRAVA_REFRESH_TOKEN']
        client_id = account['STRAVA_CLIENT_ID']
        client_secret = account['STRAVA_CLIENT_SECRET']
        expires_at = account['STRAVA_EXPIRES_AT']

        title, description = scrape.get_title_and_description(credential, runner_id)

        if title:
            # Ensure that the token is valid before making API calls
            access_token, refresh_token, expires_at = strava.ensure_valid_token(client_id, client_secret, access_token, refresh_token, expires_at)

            # Update the account with the new tokens
            account['STRAVA_ACCESS_TOKEN'] = access_token
            account['STRAVA_REFRESH_TOKEN'] = refresh_token
            account['STRAVA_EXPIRES_AT'] = expires_at

            activities = strava.get_activities(access_token)

            if len(activities) == 1:
                activity_id = activities[0]['id']
                activity_description = strava.get_activity(access_token, activity_id)['description']

                if activity_description:
                    new_description = f"""{activity_description}

{description}"""
                else:
                    new_description = description

                strava.update_activity(access_token, activity_id, title, new_description)

    # Save updated tokens
    save_users(credential, users)


@app.function_name("timer")
@app.schedule(
    schedule="%TriggerSchedule%", 
    arg_name="timer", 
    run_on_startup=False,
    use_monitor=False
) 
def timer_trigger(timer: func.TimerRequest) -> None:
    main()

@app.function_name("http")
@app.route(route="runtest", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    main()
    print("HTTP function ran.")
    return func.HttpResponse(status_code=204)  # 204 No Content