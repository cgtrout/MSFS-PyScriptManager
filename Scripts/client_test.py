import requests
import time

# Endpoint URL
url = "http://localhost:40001/latest"

# Variable to store the last received message
last_message = None

while True:
    try:
        # Send GET request to the server
        response = requests.get(url)
        
        # Check if the request was successful
        if response.status_code == 200:
            current_message = response.text
            
            # Check if the message has changed
            if current_message != last_message:
                print("New message received:", current_message)
                last_message = current_message
            else:
                print("No new message.")
        else:
            print(f"Failed to retrieve data. Status code: {response.status_code}")

    except Exception as e:
        print("An error occurred:", e)
    
    # Wait before polling again
    time.sleep(5)  # Poll every 5 seconds
