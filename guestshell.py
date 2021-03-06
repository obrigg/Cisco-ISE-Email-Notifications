import os
import time
import requests
import json
from pprint import pprint
requests.packages.urllib3.disable_warnings()
import smtplib, ssl

# ========= CHANGE US ===========
ise_ip = os.environ.get('ISE_IP','10.10.20.70')
pxgrid_user = os.environ.get('PXGRID_USER',"ise_to_mail")
smtp_server = os.environ.get('SMTP_SERVER',"smtp.gmail.com")
smtp_port = os.environ.get('MAIL_PORT', 465)
mail_username = os.environ.get('MAIL_USER')
mail_password = os.environ.get('MAIL_PASS')
mail_destination = os.environ.get('MAIL_DEST')
"""
=== GUESTSHELL INSTRUCTIONS ===

1. enable guestshell on the switch
2. make sure python3 is available ('guestshell run python -V' or 'guestshell run python3 -V')
3. pip install requests
4. enter guestshell:
    4a. create a directory: mkdir /bootflash/guest-share/ise_to_mail
    4b. create a directory: mkdir /bootflash/guest-share/ise_to_mail/data
    4c. use 'vi /bootflash/guest-share/ise_to_mail/run.py' to create a new
        python file, copy and paste the content of this file in the new file.
    4d. use 'vi /bootflash/guest-share/ise_to_mail/data/env.sh' to create an
        environment variables file.
    4e. use 'vi ~/.bashrc' to add 'source <path to env.sh>' that will use
        the env variables everytime guestshell starts.
5. create an EEM applet that will run the script every 10 minutes:
    conf t
     event manager applet ise_to_mail
      event timer cron cron-entry "*/10 * * * *"
      action 1.0 cli command "enable"
      action 2.0 cli command "guestshell run python3 /bootflash/guest-share/ise_to_mail/run.py"
      action 3.0 syslog msg "Running the ISE_to_MAIL script"

"""

def create_pxgrid_password():
    url = f"https://{ise_ip}:8910/pxgrid/control/AccountCreate"
    data = '{"nodeName": "%s"}' % pxgrid_user
    response = requests.post(url=url, headers=headers, data=data, verify=False)
    if response.status_code == 409:
        print (f"\033[0;33;40mThe PxGrid user {pxgrid_user} already exists. Kindly delete it and try again\033[0m")
        raise Exception (f"The PxGrid user {pxgrid_user} already exists. Kindly delete it and try again")
    elif response.status_code == 503:
        print (f"\033[1;31;40muser/password PxGrid is not enabled. Enable it on ISE > administration > PxGrid services > settings\033[0m")
        raise Exception (f"user/password PxGrid is not enabled. Enable it on ISE > administration > PxGrid services > settings")
    elif response.status_code != 200:
        print (f"\033[1;31;40mAn error has occured while creating the PxGrid user:\
            \n\033[0m{response.text}")
        raise Exception (f"An error has occured while creating the PxGrid user:\
            \n{response.text}")
    else:
        print(f"\033[0;32;40mThe PxGrid user {pxgrid_user} was successfully created.\033[0m")
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
            print(f"\033[1;31;40mAn error has occured while activating the PxGrid user:\
                \n\033[0m{response.text}")
            break
        elif response.json()['accountState'] == "PENDING":
            print(f"\033[0;33;40mWaiting for PxGrid user to be approved on ISE. Trying again in {str(n)} seconds.")
            print(f"On ISE go to Administration > PxGrid services, mark and approve {pxgrid_user}.\033[0m\n")
            time.sleep(n)
            n = n * 2
        elif response.json()['accountState'] == "ENABLED":
            print("\033[0;32;40mPxGrid user approved!\033[0m")
            is_activated = True
        else:
            print(f"\033[1;31;40mERROR: We shouldn't have got here...\
                \n\033[0m{response.json()}")
        if n > 3600:
            raise Exception ("it's been too long... exiting")


def service_lookup(service):
    url = f"https://{ise_ip}:8910/pxgrid/control/ServiceLookup"
    data = json.dumps({"name": service})
    response = requests.post(url=url, headers=headers, data=data, verify=False,
            auth=requests.auth.HTTPBasicAuth(pxgrid_user, pxgrid_password))
    if response.status_code != 200:
        print(f"\033[1;31;40mAn error has occured while retrieving service node:\
            \n\033[0m{response.text}")
        raise Exception (f"An error has occured while retrieving service node")
    else:
        return(response.json()['services'][0]['nodeName'])


def get_pxgrid_secret(node):
    url = f"https://{ise_ip}:8910/pxgrid/control/AccessSecret"
    data = json.dumps({"peerNodeName": node})
    response = requests.post(url=url, headers=headers, data=data, verify=False,
            auth=requests.auth.HTTPBasicAuth(pxgrid_user, pxgrid_password))
    if response.status_code != 200:
        raise Exception (f"\033[1;31;40mAn error has occured while retrieving PxGrid secret:\033[0m\n{response.text}")
    else:
        print("\033[0;32;40mThe PxGrid secret was successfully retrieved.\033[0m")
        return(response.json()['secret'])


def get_radius_failures():
    url = f"https://{ise_ip}:8910/pxgrid/ise/radius/getFailures"
    data = '{}' # {"startTimestamp": "2020-10-27T14:18:50Z"}
    response = requests.post(url=url, headers=headers, data=data, verify=False,
            auth=requests.auth.HTTPBasicAuth(pxgrid_user, pxgrid_secret))
    if response.status_code != 200:
        print(f"\033[1;31;40mAn error has occured while retrieving failures:\n\033[0m{response.text}")
        raise Exception (f"An error has occured while retrieving failures:\n\n\n{response.text}")
    else:
        print("\033[0;32;40mSuccessfully pulled the failure list.\033[0m")
        return(response.json()['failures'])


def process_failures(failures):
    message = "Subject: RADIUS Failure Report\n\nNew Radius failures were detected:\n"
    for fail in failures:
        try:
            message += f"""
            Timestamp:                   {fail['timestamp']}
            NAS IP:                      {fail['nasIpAddress']}
            NAS Name:                    {fail['nasName']}
            NAS Port:                    {fail['nasPortId']}
            Username:                    {fail['userName']}
            Calling Station Id:          {fail['callingStationId']}
            Original Calling Station Id: {fail['originalCallingStationId']}
            Message Code:                {fail['messageCode']}
            =========================================================\n\n"""
        except:
            message+= f"This failure was not parsed correctly, enclosed the original: \
                \n{str(fail)}\n\n"
    print(f"The following email will be sent from: {mail_username} to: {mail_destination}\
        \n\n{message}")
    send_email(message)


def send_email(message):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
        server.login(mail_username, mail_password)
        server.sendmail(from_addr=mail_username, to_addrs=mail_destination, msg=message)


if __name__ == "__main__":
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    print(f"Using ISE: {ise_ip}")
    try:
        with open(f'./data/{ise_ip}-pass.txt', 'r') as f:
            pxgrid_password = f.read()
    except:
        print(f"Not able to acces the pxGrid password file {ise_ip}-pass.txt, assuming user {pxgrid_user} does not exist.")
        pxgrid_password = create_pxgrid_password()
        with open(f'./data/{ise_ip}-pass.txt', 'w') as f:
            f.write(pxgrid_password)
    activate_account()
    node = service_lookup("com.cisco.ise.radius")
    pxgrid_secret = get_pxgrid_secret(node)
    last_fail_id = "0"
    print("\n\n\n\t\tPreparation complete - Now let's get to business...\n\n\n")
    new_failures = []
    try:
        failures = get_radius_failures()
        for failure in failures:
            if int(failure['id']) > int(last_fail_id):
                new_failures.append(failure)
                last_fail_id = failures[0]['id']
    except:
        print("\033[1;31;40mAn error has occurred - not able to retrieve radius failures\033[0m")
    #
    if len(new_failures) == 0:
        print(f"Woo Hoo! No new failures!\nWait.. that's means I have nothing to do..\
            \nI'll just sit here. Alone. In the dark... \n\n")
    else:
        print(f"Found {len(new_failures)} new RADIUS failures.")
        try:
            process_failures(new_failures)
        except:
            print("\033[1;31;40mAn error has occurred - not able to send an email\033[0m")
