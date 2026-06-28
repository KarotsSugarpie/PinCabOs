# PinCabOS WebApp modular refactor

## Structure

- `app.py` : noyau Flask, layout, helpers partagés et enregistrement des modules.
- `pincabos_webapp_audio.py` : Audio / SSF V2, ALSA, PipeWire, WAV test et SSF Commander.
- `pincabos_webapp_inputs.py` : Inputs, HID et Map Commander.
- `pincabos_webapp_firstrun.py` : assistant Premier Démarrage.
- `pincabos_webapp_updates.py` : pages et jobs de mise à jour.
- `pincabos_webapp_dev_admin.py` : routes Développeur et Admin.
- `pincabos_webapp_exports.py` : export de table V7 sécurisé.
- `validate_refactor.py` : validation statique incluse.
- `app.original.py` : sauvegarde immuable du fichier reçu.

## Installation cabinet

1. Faire une sauvegarde de `/opt/pincabos/web`.
2. Copier **tous** les fichiers `.py` fournis dans `/opt/pincabos/web`.
3. Valider avant de redémarrer le service :

```bash
cd /opt/pincabos/web
python3 -m py_compile app.py pincabos_webapp_*.py validate_refactor.py
python3 validate_refactor.py
```

Le module de validation confirme la syntaxe, les routes critiques et l’absence de routes/fonctions top-level dupliquées.
