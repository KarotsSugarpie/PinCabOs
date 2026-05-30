# PinCabOS WebApp refactor plan

Objectif : réduire progressivement `app.py` sans casser la WebApp.

## Règles

- Ne jamais déplacer une grosse section sans test.
- Un module à la fois.
- Toujours tester avec `deploy-webapp.sh`.
- Toujours garder rollback disponible.
- Commit Git après chaque étape fonctionnelle.

## Structure cible

- `routes/` : routes Flask par section.
- `services/` : logique système, fichiers INI, commandes, parsing.
- `templates/` : pages HTML/Jinja si séparation future.
- `static/` : CSS/JS/images existants.

## Ordre recommandé

1. Routes simples : version, help, about.
2. Console / root password.
3. Network / WiFi.
4. FullDMD.
5. Audio / SSF.
6. GPU / screens.
7. DOF / Outputs.
8. Tools / import-table / commander.

## Branches

- `main` : stable.
- `dev-webapp` : développement.
