import os
import time as t
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from io import BytesIO
import pytz
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
import logging
import random
import time

def get_blob_service_client(credential):
    return BlobServiceClient(account_url=os.getenv("AZURE_STORAGE_ACCOUNT_URL"), credential=credential)

def download_blob_content(blob_client):
    blob_content = blob_client.download_blob().readall()
    return blob_content.decode('utf-8').splitlines()

def upload_blob_content(blob_client, content):
    blob_client.upload_blob("\n".join(content), overwrite=True)

def get_current_time():
    spoof_time = os.getenv('SPOOF_TIME')
    if spoof_time == '1':
        spoofed_time_str = os.getenv('SPOOFED_TIME')
        return datetime.strptime(spoofed_time_str, '%Y-%m-%d %H-%M').replace(tzinfo=pytz.timezone('Europe/London'))
    else:
        return datetime.now(tz=pytz.timezone('Europe/London'))

def load_configuration(config_file='config.json'):
    with open(os.path.join(os.path.dirname(__file__), config_file), 'r') as file:
        config = json.load(file)
    return config

def is_time_to_run(config):
    current_time = get_current_time()
    current_day = current_time.strftime('%Y-%m-%d')
    current_hour = current_time.hour
    
    if current_time.weekday() == 5 and 9 <= current_hour < 17:
        return True
    
    if current_day in config['additional_dates'] and 9 <= current_hour < 17:
        return True
    
    return False

def has_completed_today(credential, runner_id):
    blob_service_client = get_blob_service_client(credential)
    blob_client = blob_service_client.get_blob_client(container=os.getenv("CONTAINER"), blob='logs.csv')

    try:
        logs = download_blob_content(blob_client)
    except Exception as e:
        return False

    today_date = get_current_time().strftime('%Y-%m-%d')

    for log in logs:
        log_date, log_runner_id = log.strip().split(',')
        if log_date.startswith(today_date) and log_runner_id == runner_id:
            return True

    return False

def log_completion(credential, runner_id):
    blob_service_client = get_blob_service_client(credential)
    blob_client = blob_service_client.get_blob_client(container=os.getenv("CONTAINER"), blob='logs.csv')

    try:
        logs = download_blob_content(blob_client)
    except Exception as e:
        logs = []

    log_date = get_current_time().strftime('%Y-%m-%d %H:%M:%S')
    logs.append(f"{log_date},{runner_id}")

    # Ensure the list size is no more than 2000 lines
    if len(logs) > 2000:
        logs = logs[-2000:]

    upload_blob_content(blob_client, logs)

def fetch_webpage(url):
    api_key = os.getenv("SCRAPERAPI_KEY")

    payload = {'api_key': api_key, 'url': url}
    
    try:
        r = requests.get('https://api.scraperapi.com/', params=payload, timeout=70)
        r.raise_for_status()  # Raise an HTTPError for bad responses
        logging.info(r.status_code)
        return r.text
    except Exception as err:
        logging.info(f"Other error occurred: {err}")
        raise

def store_page(credential, html_content, file_name):
    blob_service_client = BlobServiceClient(account_url=os.getenv('AZURE_STORAGE_ACCOUNT_URL'), credential=credential)
    container_client = blob_service_client.get_container_client(os.getenv('CONTAINER'))

    try:
        blob_client = container_client.get_blob_client(file_name)
        blob_client.upload_blob(html_content, overwrite=True)
        logging.info(f"Stored page content to blob {file_name}")
    except Exception as e:
        logging.info(f"Error storing page content to blob: {e}")

def fetch_and_store_parkrun_results(credential, recent_parkrun_link, runner_id):
    parts = recent_parkrun_link.strip('/').split('/')
    location = parts[-3]
    number = parts[-1]

    file_name = f'parkruns_{location}_{number}.html'

    # Check if the file already exists in blob storage
    blob_service_client = BlobServiceClient(account_url=os.getenv('AZURE_STORAGE_ACCOUNT_URL'), credential=credential)
    container_client = blob_service_client.get_container_client(os.getenv('CONTAINER'))
    blob_client = container_client.get_blob_client(file_name)

    try:
        blob_client.get_blob_properties()
        logging.info(f"File {file_name} already exists in blob storage.")
    except ResourceNotFoundError:
        # Fetch the recent parkrun results page
        recent_html_content = fetch_webpage(recent_parkrun_link)
        # Store the HTML content in Azure Blob Storage
        store_page(credential, recent_html_content, file_name)

    return file_name  # Return the blob name instead of the path

def parse_html_file(credential, file_name):
    blob_service_client = BlobServiceClient(account_url=os.getenv('AZURE_STORAGE_ACCOUNT_URL'), credential=credential)
    container_client = blob_service_client.get_container_client(os.getenv('CONTAINER'))
    blob_client = container_client.get_blob_client(file_name)

    try:
        html_content = blob_client.download_blob().readall()
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup
    except Exception as e:
        logging.info(f"Error reading HTML content from blob: {e}")
        return None

def extract_runner_stats(soup):
    # Extract total parkruns
    total_parkruns = None
    total_parkruns_tag = soup.find('h3', string=lambda text: 'parkruns total' in text if text else False)
    if total_parkruns_tag:
        total_parkruns = total_parkruns_tag.text.split()[0]
    
    # Extract most recent parkrun details
    recent_parkrun_date = None
    recent_parkrun_link = None
    recent_parkrun_location = None
    total_position = None
    gender_position = None
    age_grade_score = None
    time = None

    recent_parkrun_table = soup.find('table', {'class': 'sortable'})
    if recent_parkrun_table:
        recent_row = recent_parkrun_table.find_all('tr')[1]  # Assuming the first row is the header
        cells = recent_row.find_all('td')

        if cells:
            # Extracting the link, date, and location from the first and second `td`
            recent_parkrun_location = cells[0].get_text(strip=True).replace(' parkrun', '')
            recent_parkrun_date_tag = cells[1].find('a', href=True, target='_top')
            if recent_parkrun_date_tag:
                recent_parkrun_date = recent_parkrun_date_tag.text
                recent_parkrun_link = recent_parkrun_date_tag['href']

            gender_position = cells[2].text
            total_position = cells[3].text
            time = cells[4].text
            age_grade_score = cells[5].text

    # Extract gender
    gender = None
    gender_text = soup.find(string=lambda string: 'Most recent age category was' in string)
    if gender_text:
        category_text = gender_text.strip()
        if category_text.startswith('Most recent age category was'):
            category = category_text.split()[-1]
            if category.startswith('SM'):
                gender = 'Male'
            elif category.startswith('SW'):
                gender = 'Female'

    return {
        'total_parkruns': total_parkruns,
        'recent_parkrun_date': recent_parkrun_date,
        'recent_parkrun_link': recent_parkrun_link,
        'recent_parkrun_location': recent_parkrun_location,
        'total_position': total_position,
        'gender_position': gender_position,
        'time': time,
        'age_grade_score': age_grade_score,
        'gender': gender
    }

def extract_parkrun_stats(credential, file_name, runner_id):
    # Use parse_html_file to load the HTML content from blob storage
    soup = parse_html_file(credential, file_name)

    script_tag = soup.find('script', string=lambda string: string and 'var parkrunResultsData' in string)
    if not script_tag:
        return {
            'total_runners': None,
            'male_runners': None,
            'female_runners': None,
            'is_pb': False
        }

    script_content = script_tag.string
    json_str = script_content.split('var parkrunResultsData = ', 1)[1].rsplit(';', 1)[0]
    parkrun_results_data = json.loads(json_str)

    gender_counts = parkrun_results_data.get('genderCounts', {})
    male_runners = gender_counts.get('Male', 0)
    female_runners = gender_counts.get('Female', 0)
    
    total_runners = 0
    last_runner_tag = soup.find_all('tr', {'class': 'Results-table-row'})[-1]
    if last_runner_tag:
        last_position = last_runner_tag.find('td', {'class': 'Results-table-td--position'})
        if last_position:
            total_runners = last_position.text.strip()

    # Find all rows
    runner_tags = soup.find_all('tr', {'data-name': True})

    position = None
    gender_position = None

    # Iterate over all runner tags
    for runner_tag in runner_tags:
        href_tag = runner_tag.find('a', href=True)
        if href_tag:
            href = href_tag['href']
            if f"/parkrunner/{runner_id}" in href:
                # Extract the position and gender position
                position = runner_tag['data-position']

                # Find the gender position within the nested structure
                detailed_div = runner_tag.find('div', class_='detailed')
                if detailed_div:
                    # Extract gender position by looking for matching structure
                    gender_span = detailed_div.find('span', class_='Results-table--M')
                    if gender_span:
                        gender_position_text = gender_span.next_sibling.strip()
                        if gender_position_text.isdigit():
                            gender_position = int(gender_position_text)

                # Check if the runner has a New PB!
                if runner_tag.get('data-achievement') == "New PB!":
                    is_pb = True

                break

    return {
        'total_runners': total_runners,
        'male_runners': male_runners,
        'female_runners': female_runners,
        'position': position,
        'gender_position': gender_position,
        'is_pb': is_pb
    }

def get_title_and_description(credential, runner_id):
    url = f"https://www.parkrun.org.uk/parkrunner/{runner_id}/"

    config = load_configuration()

    if not is_time_to_run(config):
        logging.info("Not within the allowed time frame.")
        return None, None

    if has_completed_today(credential, runner_id):
        logging.info(f"Processing already completed for runner ID: {runner_id} today.")
        return None, None
    
    file_name = f'runner_{runner_id}.html'
    # Fetch runner profile and store it in Azure Blob Storage
    html_content = fetch_webpage(url)
    store_page(credential, html_content, file_name)
    
    soup = parse_html_file(credential, file_name)
    data = extract_runner_stats(soup)

    recent_parkrun_date = datetime.strptime(data['recent_parkrun_date'], '%d/%m/%Y').date() if data['recent_parkrun_date'] else None
    
    if recent_parkrun_date == get_current_time().date():
        if data['recent_parkrun_link']:
            file_name = fetch_and_store_parkrun_results(credential, data['recent_parkrun_link'], runner_id)
            parkrun_stats = extract_parkrun_stats(credential, file_name, runner_id)

            title = f"Parkrun #{data['total_parkruns']} ({data['recent_parkrun_location']})"
            
            description = f"""🕒 Official time: {data['time']}
🏁 Overall position: {parkrun_stats['position']}/{parkrun_stats['total_runners']}
🚹 Gender position: {parkrun_stats['gender_position']}/{parkrun_stats['male_runners'] if data['gender'] == 'Male' else parkrun_stats['female_runners']}
🎯 Age grade: {data['age_grade_score']}
👦 Automated statistics powered by Isaac"""
            
            if parkrun_stats['is_pb']:
                description = description.replace(f"🕒 Official time: {data['time']}", f"🕒 Official time: {data['time']} | Course PB 🚨")

            log_completion(credential, runner_id)

            return title, description

    else:
        logging.info("The most recent parkrun did not occur today. Skipping additional data fetch.")
        return None, None
