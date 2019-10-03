#Python Script to send notification to users using FCM Tokens

!pip install six python-firebase #if executing on Google Colab
from firebase import firebase
import requests

def data_template(fcmToken, title, description, bigPicture):
	data = '{"to":"' + fcmToken + '","priority":"high","data":{"title":"' + title + '","description":"' + description + '","bigPicture":"' + bigPicture + '"}}'
	return data.encode('utf-8')

firebase = firebase.FirebaseApplication('https://your-project-url.firebaseio.com', None) #add your project url

access_token = "Enter Firebase Legacy Server Key" # Use Legacy Server Key on your Project Settings -> Cloud Messaging
headers = {"Content-Type" : "application/json", "authorization" : "key=" + access_token}

fcmTokens = firebase.get("/fcmTokens", None) #FCM Tokens stored in Realtime Database

title = "Title of the Notification"
description = "Description of the Notification"
bigPicture = "URL of the picture to be sent along with the Notification" #Optional

url = "https://fcm.googleapis.com/fcm/send"

""" Unblock to send test fcm message
test_token = "test FCM Token"

r = requests.post(url, data=data_template(test_token, title, description, bigPicture) , headers=headers)

print(r)
"""

for token in fcmTokens.items():
	print (token)
	data_to_send = data_template(token[1], title, description, bigPicture)
	r = requests.post(url, data=data_to_send , headers=headers)
	print ( token[0] + " >>> " + str(r) )
	#print (data)

# data_template = {"to":"fcmToken","data":{"title":"Title","description":"Text Description","bigPicture":"bigpictureUrl"}}
