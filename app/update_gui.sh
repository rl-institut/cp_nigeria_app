#!/usr/local/bin/python3
python3 manage.py compilemessages
python3 manage.py makemigrations users projects dashboard && \
python3 manage.py migrate && \
python3 manage.py collectstatic && \
echo 'Updated the open-plan GUI app successfully!!'
