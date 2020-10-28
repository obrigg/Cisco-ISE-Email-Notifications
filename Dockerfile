FROM python:3.7-slim-buster
RUN apt-get update && apt-get install -y git
#TODO
RUN git clone https://github.com/obrigg/Cisco-ISE-Email-Notifications.git
WORKDIR /Cisco-ISE-Email-Notifications/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
ENTRYPOINT ["python", "email-failure.py"]
