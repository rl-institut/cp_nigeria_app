#!/usr/local/bin/python
python manage.py compilemessages
python manage.py migrate && \
python manage.py collectstatic && \
echo 'Updated the WEFEgui app successfully!!'
