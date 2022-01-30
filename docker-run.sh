#!/bin/bash

COVENANT_ROOT="${COVENANT_ROOT:-"/etc/covenant"}"
COVENANT_CONFFILE="${COVENANT_CONFFILE:-"${COVENANT_ROOT}/covenant.yml"}"

mkdir -p "${COVENANT_ROOT}"

cd "${COVENANT_ROOT}"

if [[ ! -f "${COVENANT_CONFFILE}" ]] && [[ ! -z "${COVENANT_CONFIG}" ]];
then
    echo -e "${COVENANT_CONFIG}" > "${COVENANT_CONFFILE}"
fi

exec covenant -f ${COVENANT_EXTRA_OPTS}
