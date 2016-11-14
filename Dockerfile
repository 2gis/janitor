FROM alpine:3.3

MAINTAINER IO Team 2GIS <io@2gis.ru>

RUN apk update \
    && apk upgrade \
    && apk add \
        gcc \
        curl \
        py-pip python

ENV TERM=xterm

COPY janitor.py /opt/janitor/janitor.py
COPY requirements.txt /opt/janitor/requirements.txt

RUN pip install -r /opt/janitor/requirements.txt

ENTRYPOINT ["python", "/opt/janitor/janitor.py"]

