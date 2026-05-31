# PinCabOS screens config

Ce dossier contient la configuration écran PinCabOS.

Fichiers attendus :
- `screens.json` : mapping logique Playfield / Backglass / DMD
- `screens.env` : variables shell équivalentes
- `layout.conf` : layout X11/NVIDIA/AMD/Intel utilisé par les scripts

Sur un nouveau cab, ces fichiers peuvent être régénérés par :
- `/opt/pincabos/tools/auto-detect-screens.sh`
- ou par la page GPU/Écrans de la WebApp.
