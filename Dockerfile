# Use official Python image
FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD gunicorn wsgi:app --bind 0.0.0.0:$PORT
