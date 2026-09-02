# Production secrets

Create these files on the production server:

- `django_secret_key.txt` — generate with `openssl rand -base64 48 | tr -d '\n'`
- `postgres_password.txt` — generate with `openssl rand -base64 36 | tr -d '\n'`
- `smtp_password.txt` — enter the SMTP/app password without a trailing newline

The `*.txt` files in this directory are ignored by Git. Never commit real secrets.

For file-backed Docker Compose secrets, use:

```bash
chmod 700 secrets
chmod 644 secrets/*.txt
```

The directory remains private on the host, while the non-root application user can
read the individual files after Docker mounts them at `/run/secrets/`.
