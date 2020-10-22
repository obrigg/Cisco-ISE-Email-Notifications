import os
import time
import requests
from pprint import pprint
requests.packages.urllib3.disable_warnings()
import smtplib, ssl

# ===============================
ise_admin = os.environ.get('ISE_USER','admin')
ise_pass = os.environ.get('ISE_PASS','C1sco12345!')
ise_ip = os.environ.get('ISE_IP','10.10.20.70')
pxgrid_user = "pxgrid_user"
sleep_time = 60                 # Sleep time between checks (in seconds).
smtp_server = os.environ.get('SMTP_SERVER',"smtp.gmail.com")
smtp_port = os.environ.get('MAIL_PORT', 465)
mail_username = os.environ.get('MAIL_USER')
mail_password = os.environ.get('MAIL_PASS')
mail_destination = os.environ.get('MAIL_DEST')
# ===============================

def create_pxgrid_password():
    url = f"https://{ise_ip}:8910/pxgrid/control/AccountCreate"
    data = '{"nodeName": "%s"}' % pxgrid_user
    response = requests.post(url=url, headers=headers, data=data, verify=False)
    if response.status_code == 409:
        raise Exception (f"The PxGrid user {pxgrid_user} already exists. Kindly delete it and try again")
    elif response.status_code == 503:
        raise Exception (f"user/password PxGrid is not enabled. Enable it on ISE > administration > PxGrid services > settings")
    elif response.status_code != 200:
        raise Exception (f"An error has occured while creating the PxGrid user:\n{response.text}")
    else:
        print(f"The PxGrid user {pxgrid_user} was successfully created.")
        return(response.json()['password'])


def activate_account():
    url = f"https://{ise_ip}:8910/pxgrid/control/AccountActivate"
    data = "{}"
    is_activated = False
    n = 10
    while not is_activated:
        response = requests.post(url=url, headers=headers, data=data, verify=False, 
            auth=requests.auth.HTTPBasicAuth(pxgrid_user, pxgrid_password))
        if response.status_code != 200:
            print(f"An error has occured while activating the PxGrid user:\n{response.text}")
        elif response.json()['accountState'] == "PENDING":
            print(f"Waiting for PxGrid user to be approved on ISE. Trying again in {str(n)} seconds.")
            print(f"On ISE go to Administration > PxGrid services, mark and approve {pxgrid_user}.")
            time.sleep(n)
            n = n * 2
        elif response.json()['accountState'] == "ENABLED":
            print("PxGrid user approved!")
            is_activated = True
        else:
            print(f"ERROR: We shouldn't have got here...\n{response.json()}")
        if n > 3600:
            raise Exception ("it's been too long... exiting")


def get_pxgrid_secret():
    url = f"https://{ise_ip}:8910/pxgrid/control/AccessSecret"
    data = '{"peerNodeName": "ise-mnt-ise24"}'
    response = requests.post(url=url, headers=headers, data=data, verify=False, 
            auth=requests.auth.HTTPBasicAuth(pxgrid_user, pxgrid_password))
    if response.status_code != 200:
        print(f"An error has occured while retrieving PxGrid secret:\n{response.text}")
        raise Exception
    else:
        print("The PxGrid secret was successfully retrieved.")
        return(response.json()['secret'])


def get_radius_failures():
    url = f"https://{ise_ip}:8910/pxgrid/ise/radius/getFailures"
    data = '{}'
    response = requests.post(url=url, headers=headers, data=data, verify=False, 
            auth=requests.auth.HTTPBasicAuth(pxgrid_user, pxgrid_secret))
    if response.status_code != 200:
        print(f"An error has occured while retrieving failures:\n{response.text}")
    else:
        print("Successfully pulled the failure list.")
        return(response.json()['failures'])


def process_failures(failures):
    for fail in failures:
        send_email(str(fail))


def send_email(message):
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
        server.login(mail_username, mail_password)
        server.sendmail(mail_username, mail_destination, message)


if __name__ == "__main__":
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    pxgrid_password = create_pxgrid_password()
    activate_account()
    pxgrid_secret = get_pxgrid_secret()
    context = ssl.create_default_context()
    print("\n\n\n\t\tPreparation complete - Now let's get to business...\n\n\n")
    while True:
        failures = get_radius_failures()
        if len(failures) == 0:
            print(f"Woo Hoo! No failures!\nWait.. that's means I have nothing to do..\nI'll just sit here. Alone. In the dark... (for {sleep_time} seconds)\n\n")
        else:
            process_failures(failures)
        time.sleep(sleep_time)
