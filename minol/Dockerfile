# Playwright image ships Chromium for the Minol login page.
FROM mcr.microsoft.com/playwright/python:v1.56.0-jammy

RUN pip install --no-cache-dir paho-mqtt==2.1.0 requests==2.32.5 playwright==1.56.0

WORKDIR /app
COPY minol_client.py main.py /app/

CMD ["python3", "-u", "/app/main.py"]
