FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24

WORKDIR /usr/src/bluetti
COPY pyproject.toml setup.py setup.cfg requirements.txt README.rst LICENSE ./
COPY bluetti_mqtt/ bluetti_mqtt/
RUN apk add --no-cache --virtual .build-deps build-base linux-headers \
    && python -m pip install --no-cache-dir . \
    && apk del .build-deps \
    && python -m pip check \
    && bluetti-mqtt --help

COPY --chmod=755 run.sh /run.sh
CMD ["/run.sh"]
