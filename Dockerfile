FROM python:3.7-alpine

ENV DEBIAN_FRONTEND noninteractive
ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8

RUN pip install pipenv

RUN apk update \
    && apk --no-cache add \
        gcc \
        libressl-dev \
        libffi-dev \
        postgresql-dev \
        musl-dev

# -- Install Application into container:
RUN set -ex && mkdir /app

WORKDIR /app

# -- Adding Pipfiles
COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock

# -- Install dependencies:
RUN set -ex && pipenv install --deploy --system

COPY manager/ /app

ENTRYPOINT ["python", "manager.py"]
