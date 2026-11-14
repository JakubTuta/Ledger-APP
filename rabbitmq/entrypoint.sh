#!/bin/sh
# Sets the byte cap on the ingestion queues once the broker is up, then hands over to the stock entrypoint.
# A policy rather than a queue argument: changing x-* arguments on a declared durable queue fails with
# PRECONDITION_FAILED. rabbitmq.conf cannot carry it, and load_definitions would stop the broker
# from creating RABBITMQ_DEFAULT_USER/VHOST.
(
  export HOME=/var/lib/rabbitmq
  until rabbitmqctl await_startup >/dev/null 2>&1; do sleep 2; done
  rabbitmqctl set_policy ingestion-byte-cap '^ingestion[.]' '{"max-length-bytes":1073741824,"overflow":"reject-publish"}' --apply-to queues
) &
exec docker-entrypoint.sh rabbitmq-server
