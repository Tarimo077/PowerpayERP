# Production secrets

Create these files on the production server:

- `django_secret_key.txt` — generate with `openssl rand -base64 48 | tr -d '\n'`
- `postgres_password.txt` — generate with `openssl rand -base64 36 | tr -d '\n'`
- `smtp_password.txt` — enter the SMTP/app password without a trailing newline

The `*.txt` files in this directory are ignored by Git. Never commit real secrets.
