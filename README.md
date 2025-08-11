# Kubernetes_argocd_template
Template for jobs in kubernetes

#### Instrucciones de uso:

Paso 1: Crear un user y una password en docker.io para incluirlos en el repositorio como secretos de acceso a docker. Posteriormente, el propio repositorio lo usará en este paso:

username: ${{ secrets.DOCKER_HUB_USERNAME }}

password: ${{ secrets.DOCKER_HUB_ACCESS_TOKEN_2 }}

Es importante que tengan el mismo nombre, si se cambia se debe también cambiar en build-and-push.yml

Paso 2: Modificar el nombre de la carpeta que contendrá el código y el cronjob.yaml. Es importante utilizar nombres representativos de manera que cuando se genere la app en argo, se pueda identificar todo con claridad.

Paso 3: Revisar si son necesarios secretos nuevos para acceso a API's. En ese caso, revisar el código https://github.com/carlosmorenobarrado/cryto_data_extraction_load.git que ya tiene secretos incluidos. El siguiente contenido es el usado de gemini para realizar la codificación:

## Paso 1: Crea el archivo YAML local
En tu terminal, crea un archivo llamado secreto-temporal.yaml. Puedes usar el editor que prefieras (como nano o vim), o simplemente copiar y pegar.

Este archivo es temporal y NUNCA lo subirás a GitHub.

secreto-temporal.yaml:

YAML

apiVersion: v1
kind: Secret
metadata:
  name: cryto-data-ext-ld-secrets
  namespace: default
data:

  API_KEY: PEGA_AQUI_TU_API_KEY_EN_BASE64
  API_SECRET: PEGA_AQUI_TU_API_SECRET_EN_BASE64

## Paso 2: Sella el secreto
Ahora, desde tu terminal, ejecuta este comando. Asegúrate de estar en el mismo directorio donde guardaste el archivo secreto-temporal.yaml.

Bash

kubeseal < secreto-temporal.yaml > kubernetes/sealed-crypto-secret.yaml
Este comando hace lo siguiente:

Lee tu secreto-temporal.yaml.

Lo encripta.

Guarda el resultado en un nuevo archivo llamado sealed-crypto-secret.yaml directamente dentro de tu carpeta kubernetes/.

## Paso 3: Sube el archivo seguro a GitHub
Ya puedes borrar el archivo temporal si quieres (rm secreto-temporal.yaml).

Ahora, sube a tu repositorio el nuevo archivo sellado, que es 100% seguro de compartir.

Bash

## Añade el nuevo secreto sellado al repositorio
git add kubernetes/sealed-crypto-secret.yaml

## Crea el commit
git commit -m "feat: Add encrypted application secrets"
git push