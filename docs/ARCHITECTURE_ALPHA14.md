# PinCabOS Alpha 1.4 Architecture

## Objectif

Alpha 1.4 stabilise :
- WebApp PinCabOS sur nginx port 80
- backend gunicorn via socket Unix `/run/pincabos-web.sock`
- VPinFE comme frontend principal
- VPX Linux x64 comme moteur
- chemins utilisateur modernes sous `/home/pinball`
- suppression des ghosts Alpha 1.1 (`OLD_ALPHA11_OPT_PINCABOS_VPINBALL`, imports/exports anciens, ancien backend TCP supprimé)

## Chemins principaux

- WebApp : `/opt/pincabos/web`
- Tools : `/opt/pincabos/tools`
- Wrappers : `/opt/pincabos/bin`
- Config : `/opt/pincabos/config`
- VPX runtime : `/opt/pincabos/apps/vpx`
- VPinFE runtime : `/opt/pincabos/apps/frontend/vpinfe`
- Tables : `/home/pinball/Tables`
- VPX user config : `/home/pinball/.vpinball`
- VPinFE config : `/home/pinball/.config/vpinfe/vpinfe.ini`

## Services

- `pincabos-web.service`
- `pincabos-frontend.service`
- `pincabos-console.service`
- `pincabos-screen-layout.service`

## Non versionné

- tables VPX
- ROMs
- PuPVideos
- VPX/VPinFE upstream binaries lourds
- caches
- logs
- backups
- secrets/API keys
