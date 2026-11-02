# Publicación temporal de WAKI

## Requisitos

- Docker y Docker Compose funcionando.
- cloudflared instalado.
- Archivo .env configurado y excluido de Git.
- Contraseña del administrador configurada.
- AUTH_COOKIE_SECURE=true para ingresar mediante HTTPS.

## Iniciar el servidor

Desde la raíz del repositorio:

```bash
docker compose up -d
docker compose ps
curl -fsS http://localhost:8000/api/health
```

Para aplicar cambios en el código del servidor:

```bash
docker compose up --build -d
```

## Publicar por HTTPS

En otra terminal:

```bash
cloudflared tunnel --url http://localhost:8000
```

Abrir la dirección https://…trycloudflare.com que aparece.

Mantener Docker y el túnel activos, con la laptop encendida,
conectada a internet y sin suspensión.

## Detener la publicación

Presionar Ctrl+C en la terminal del túnel.

Esto detiene el acceso público, pero no elimina los datos.
Para detener también el servidor:

```bash
docker compose stop waki
```
