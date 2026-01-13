web: gunicorn wsgi:app --workers 2 --worker-class sync --timeout 120 --bind 0.0.0.0:$PORT --access-logfile - --error-logfile - --log-level info
worker: celery -A tasks worker --loglevel=INFO
beat: celery -A tasks beat --loglevel=INFO
