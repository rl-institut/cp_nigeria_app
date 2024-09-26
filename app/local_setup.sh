#!/usr/local/bin/python
echo yes | python manage.py collectstatic && \
python manage.py compilemessages
python manage.py makemigrations users projects dashboard && \
python manage.py migrate && \
python manage.py update_assettype && \
python manage.py update_bmquestions && \
python manage.py loaddata 'fixtures/multivector_fixture.json' && \
python manage.py cp_setup && \
echo 'Completed Setup Successfully!!'
