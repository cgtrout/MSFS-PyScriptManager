import requests
import time

# Endpoint URL
url = "http://localhost:40001/latest"

# Polling to get the next message in the queue
def poll_for_messages():
    while True:
        try:
            # Send GET request to the server
            response = requests.get(url)
            
            if response.status_code == 200:
                # Process the received message
                print("New message received:", response.text)
            elif response.status_code == 204:
                print("No new messages.")
            else:
                print(f"Failed to retrieve data. Status code: {response.status_code}")
        except Exception as e:
            print("An error occurred:", e)
        
        time.sleep(2)  # Poll every 2 seconds

# Start polling
if __name__ == "__main__":
    poll_for_messages()
