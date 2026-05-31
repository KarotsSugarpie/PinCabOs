#!/bin/bash
set -e

NEWPASS="$(cat)"

NEWPASS="$(echo "$NEWPASS" | tr -d '\r' | head -n 1)"

if [ -z "$NEWPASS" ]; then
  echo "ERREUR: mot de passe vide interdit."
  exit 1
fi

if [ ${#NEWPASS} -lt 6 ]; then
  echo "ERREUR: mot de passe trop court. Minimum 6 caractères."
  exit 1
fi

echo "root:${NEWPASS}" | /usr/sbin/chpasswd

echo "Mot de passe root changé avec succès."
