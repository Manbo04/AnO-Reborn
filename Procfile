web: gunicorn wsgi:app --workers 4 --threads 2 --worker-class gthread --timeout 120 --bind 0.0.0.0:$PORT --access-logfile - --error-logfile - --log-level info --keep-alive 30
worker: celery -A tasks worker --loglevel=INFO
beat: celery -A tasks beat --loglevel=INFO
