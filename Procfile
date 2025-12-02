web: gunicorn wsgi:app --workers 4 --timeout 120 --bind 0.0.0.0:$PORT
worker: celery -A tasks.celery worker --loglevel=INFO
beat: celery -A tasks.celery beat --loglevel=INFO
