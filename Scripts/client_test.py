import requests

# Endpoint URL
url = "http://localhost:8080/latest"

try:
    # Send GET request to the server
    response = requests.get(url)
    
    # Check if the request was successful
    if response.status_code == 200:
        print("Server Response:", response.text)
    else:
        print(f"Failed to retrieve data. Status code: {response.status_code}")

except Exception as e:
    print("An error occurred:", e)
