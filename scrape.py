import os
import time as t
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import pytz

# Define the path to the .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

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

def has_completed_today(log_file, runner_id):
    if not os.path.exists(log_file):
        return False

    with open(log_file, 'r') as file:
        logs = file.readlines()
    
    today_date = get_current_time().strftime('%Y-%m-%d')
    
    for log in logs:
        log_date, log_runner_id = log.strip().split(',')
        if log_date.startswith(today_date) and log_runner_id == runner_id:
            return True
    
    return False

def log_completion(log_file, runner_id):
    with open(log_file, 'a') as file:
        log_date = get_current_time().strftime('%Y-%m-%d %H:%M:%S')
        file.write(f"{log_date},{runner_id}\n")

def fetch_webpage(url, retries=3, delay=5):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        return response.text
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        if retries > 0 and response.status_code == 403:
            print(f"Retrying in {delay} seconds...")
            t.sleep(delay)
            return fetch_webpage(url, retries - 1, delay)
        else:
            raise
    except Exception as err:
        print(f"Other error occurred: {err}")
        raise

def store_page(html_content, file_path):
    # Store the raw HTML content into a file
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(html_content)

def parse_html_file(file_path):
    # Load HTML content from the file
    with open(file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()
    soup = BeautifulSoup(html_content, 'html.parser')
    return soup

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

def fetch_and_store_parkrun_results(recent_parkrun_link, runner_id):
    # Extract location and number from URL
    parts = recent_parkrun_link.strip('/').split('/')
    location = parts[-3]
    number = parts[-1]
    
    # Define the path for the cached parkrun file
    parkrun_dir = os.path.join(os.path.dirname(__file__), 'parkruns_files')
    file_name = f'parkruns_{location}_{number}.html'
    file_path = os.path.join(parkrun_dir, file_name)
    
    if not os.path.exists(file_path):
        # Fetch the recent parkrun results page
        recent_html_content = fetch_webpage(recent_parkrun_link)
        
        # Store the HTML content in a file named `parkruns_{location}_{number}.html`
        store_page(recent_html_content, file_path)
    
    return file_path

def extract_parkrun_stats(file_path, runner_id):
    soup = parse_html_file(file_path)

    # Extract JavaScript variable containing parkrun results data
    script_tag = soup.find('script', string=lambda string: string and 'var parkrunResultsData' in string)
    if not script_tag:
        return {
            'total_runners': None,
            'male_runners': None,
            'female_runners': None,
            'is_pb': False
        }

    script_content = script_tag.string

    # Extract JSON object from the JavaScript variable
    json_str = script_content.split('var parkrunResultsData = ', 1)[1].rsplit(';', 1)[0]
    parkrun_results_data = json.loads(json_str)

    # Extracting total runners, male runners, and female runners count
    gender_counts = parkrun_results_data.get('genderCounts', {})
    male_runners = gender_counts.get('Male', 0)
    female_runners = gender_counts.get('Female', 0)
    
    # Calculate total runners by looking at the position of the last placed runner
    total_runners = 0
    last_runner_tag = soup.find_all('tr', {'class': 'Results-table-row'})[-1]  # Assume the last row represents the last runner
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

def get_title_and_description(runner_id):
    # URL to scrape
    url = f"https://www.parkrun.org.uk/parkrunner/{runner_id}/"
    # Directories for different types of files
    runner_dir = os.path.join(os.path.dirname(__file__), 'runner_files')
    log_file = os.path.join(os.path.dirname(__file__), 'log.csv')

    # Loading configuration
    config = load_configuration()

    # Checking if it is time to run
    if not is_time_to_run(config):
        print("Not within the allowed time frame.")
        return None, None

    # Checking if the process has already completed today
    if has_completed_today(log_file, runner_id):
        print(f"Processing already completed for runner ID: {runner_id} today.")
        return None, None
    
    runner_file_path = os.path.join(runner_dir, f'runner_{runner_id}.html')
    
    # Fetch runner profile and store it
    html_content = fetch_webpage(url)
    store_page(html_content, runner_file_path)
    
    soup = parse_html_file(runner_file_path)
    data = extract_runner_stats(soup)

    # Parse the most recent parkrun date
    recent_parkrun_date = datetime.strptime(data['recent_parkrun_date'], '%d/%m/%Y').date() if data['recent_parkrun_date'] else None
    
    # Check if the recent parkrun is today's date
    if recent_parkrun_date == get_current_time().date():
        if data['recent_parkrun_link']:
            file_path = fetch_and_store_parkrun_results(data['recent_parkrun_link'], runner_id)
            parkrun_stats = extract_parkrun_stats(file_path, runner_id)

            # Create title and description
            title = f"Parkrun #{data['total_parkruns']} ({data['recent_parkrun_location']})"
            
            description = f"""🕒 Official time: {data['time']}
🏁 Overall position: {parkrun_stats['position']}/{parkrun_stats['total_runners']}
🚹 Gender position: {parkrun_stats['gender_position']}/{parkrun_stats['male_runners'] if data['gender'] == 'Male' else parkrun_stats['female_runners']}
🎯 Age grade: {data['age_grade_score']}
🍓 Automated statistics powered by Isaac's RPi"""

            if parkrun_stats['is_pb']:
                description = description.replace(f"🕒 Official time: {data['time']}", f"🕒 Official time: {data['time']} | Course PB 🚨")

            # Log the successful completion
            log_completion(log_file, runner_id)

            return title, description

    else:
        print("The most recent parkrun did not occur today. Skipping additional data fetch.")
        return None, None