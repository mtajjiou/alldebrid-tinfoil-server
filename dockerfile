FROM python:3.10-alpine

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
ENV ALLDEBRID_API_KEY=
ENV AUTH_USERNAME=admin
ENV AUTH_PASSWORD=adminadmin
ENV PORT=8000
ENV SWITCH_UID=

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips='*'", "--proxy-headers"]