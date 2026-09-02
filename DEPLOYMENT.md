# PowerpayERP production deployment

This runbook deploys PowerpayERP at `https://erp.powerpayafrica.com` using Docker Compose, PostgreSQL, Redis, Gunicorn, Nginx, and Let's Encrypt.

## 1. Prepare the server

Use a current Ubuntu LTS server with at least 2 CPU cores, 4 GB RAM, and enough disk for PostgreSQL, uploaded documents, and backups.

Install Docker Engine and the Compose plugin using Docker's official Ubuntu instructions. Confirm:

```bash
docker --version
docker compose version
```

Allow SSH, HTTP, and HTTPS through the firewall:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Do not expose PostgreSQL port 5432 or Redis port 6379.

## 2. Point DNS to the server

At the DNS provider for `powerpayafrica.com`, create:

```text
Type: A
Name: erp
Value: <SERVER_PUBLIC_IPV4>
TTL: 300 or Auto
```

Add an `AAAA` record only if IPv6 works on the server. Confirm the result before requesting TLS:

```bash
getent hosts erp.powerpayafrica.com
```

It must return the deployment server's public address.

## 3. Copy the project

Example location:

```bash
sudo mkdir -p /opt/powerpayerp
sudo chown "$USER":"$USER" /opt/powerpayerp
cd /opt/powerpayerp
git clone <YOUR_REPOSITORY_URL> .
```

Alternatively, securely copy the project contents into `/opt/powerpayerp`.

## 4. Create production configuration

```bash
cp .env.production.example .env.production
nano .env.production
```

Set the real SMTP host, account, sender, and Let's Encrypt email. Keep:

```dotenv
DEBUG=False
ALLOWED_HOSTS=erp.powerpayafrica.com
CSRF_TRUSTED_ORIGINS=https://erp.powerpayafrica.com
SITE_URL=https://erp.powerpayafrica.com
DATABASE_ENGINE=postgresql
POSTGRES_DB=powerpayerp
POSTGRES_USER=powerpayerp
```

Neither `POSTGRES_DB` nor `POSTGRES_USER` may be blank. Validate what Compose will
receive before starting containers:

```bash
grep -E '^(DATABASE_ENGINE|POSTGRES_DB|POSTGRES_USER)=' .env.production
docker compose --env-file .env.production -f compose.prod.yaml config --environment
```

Create secrets without trailing newlines:

```bash
mkdir -p secrets
openssl rand -base64 48 | tr -d '\n' > secrets/django_secret_key.txt
openssl rand -base64 36 | tr -d '\n' > secrets/postgres_password.txt
printf '%s' 'YOUR_REAL_SMTP_PASSWORD' > secrets/smtp_password.txt
chmod 700 secrets
chmod 600 .env.production
chmod 644 secrets/*.txt
```

The secret directory is accessible only to its owner (`0700`). Its files are `0644`
so the non-root UID `10001` inside the application container can read the
file-backed Compose mounts. Because other host users cannot traverse the `secrets`
directory, they still cannot read those files. Never commit `.env.production` or
the secret text files.

Confirm the application container can read the mounts before migrating:

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  run --rm --no-deps web sh -c \
  'test -r /run/secrets/django_secret_key && test -r /run/secrets/postgres_password && test -r /run/secrets/smtp_password'
```

## 5. Validate and build

Always supply the production environment file to Compose because it is also used for `${...}` interpolation:

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  config --quiet

docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  build
```

## 6. Start PostgreSQL and Redis

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  up -d db redis
```

Check their health:

```bash
docker compose --env-file .env.production -f compose.prod.yaml ps
```

## 7. Apply the production database migrations

This is the intentional one-time PostgreSQL migration step. It is not part of the web container startup command, preventing several replicas from racing each other.

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  run --rm web python manage.py migrate
```

For a brand-new database, create the platform administrator after the application starts:

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  run --rm web python manage.py createsuperuser
```

If production must contain existing SQLite data, do not copy `db.sqlite3` into PostgreSQL. Perform a tested Django `dumpdata`/`loaddata` migration or a controlled ETL process before accepting live traffic.

## 8. Collect static files

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  run --rm web python manage.py collectstatic --noinput
```

The collected files are stored in the shared `static_data` volume and served by Nginx.

## 9. Start Django and the email retry worker

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  up -d web email-retry
```

Confirm Django is healthy:

```bash
docker compose --env-file .env.production -f compose.prod.yaml ps
docker compose --env-file .env.production -f compose.prod.yaml logs --tail=100 web
```

## 10. Start temporary HTTP Nginx

The production Nginx configuration cannot start before a certificate exists. Use the bootstrap override:

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  -f deploy/compose.bootstrap.yaml \
  up -d nginx
```

Confirm this opens over HTTP:

```text
http://erp.powerpayafrica.com
```

## 11. Obtain the Let's Encrypt certificate

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  --profile tools \
  run --rm certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --domain erp.powerpayafrica.com \
  --email admin@powerpayafrica.com \
  --agree-tos \
  --no-eff-email
```

Use the real operational email if it differs from the example.

## 12. Switch to HTTPS Nginx

Recreate only Nginx without the bootstrap override:

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  up -d --force-recreate nginx
```

Verify:

```bash
curl -I https://erp.powerpayafrica.com
curl https://erp.powerpayafrica.com/healthz/
```

The health endpoint should return `{"status": "ok"}`.

## 13. Validate Django production security

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  exec web python manage.py check --deploy
```

Also test login, OTP email, employee invitations, protected receipts/documents, Swagger JWT authentication, and file uploads.

## 14. Automatic certificate renewal

Edit root's crontab:

```bash
sudo crontab -e
```

Run renewal twice daily:

```cron
17 2,14 * * * cd /opt/powerpayerp && docker compose --env-file .env.production -f compose.prod.yaml --profile tools run --rm certbot renew --webroot --webroot-path /var/www/certbot --quiet && docker compose --env-file .env.production -f compose.prod.yaml exec -T nginx nginx -s reload >> /var/log/powerpayerp-certbot.log 2>&1
```

## 15. Database and media backups

Create a backup directory:

```bash
mkdir -p backups
chmod 700 backups
```

Manual PostgreSQL backup:

```bash
docker compose \
  --env-file .env.production \
  -f compose.prod.yaml \
  exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | gzip > "backups/powerpayerp-$(date +%F-%H%M%S).sql.gz"
```

Media backup:

```bash
docker run --rm \
  -v powerpayerp_media_data:/source:ro \
  -v "$PWD/backups:/backup" \
  alpine sh -c 'tar -czf /backup/media-$(date +%F-%H%M%S).tar.gz -C /source .'
```

Copy backups to encrypted off-server storage. Test restoring both PostgreSQL and media together.

## Updating the application

Back up first, then:

```bash
cd /opt/powerpayerp
git pull --ff-only

docker compose --env-file .env.production -f compose.prod.yaml build
docker compose --env-file .env.production -f compose.prod.yaml run --rm web python manage.py migrate
docker compose --env-file .env.production -f compose.prod.yaml run --rm web python manage.py collectstatic --noinput
docker compose --env-file .env.production -f compose.prod.yaml up -d --remove-orphans
docker compose --env-file .env.production -f compose.prod.yaml exec web python manage.py check --deploy
```

## Rollback outline

1. Stop accepting writes or display a maintenance page.
2. Restore the previous application commit/image.
3. Restore the matching PostgreSQL backup if the migration is not backward-compatible.
4. Restore the matching media archive when file records changed.
5. Recreate the services and run health/security checks.

Never run destructive database rollback commands without a verified backup.

## Useful operations

```bash
# Service status
docker compose --env-file .env.production -f compose.prod.yaml ps

# Follow application logs
docker compose --env-file .env.production -f compose.prod.yaml logs -f web nginx

# Restart Django only
docker compose --env-file .env.production -f compose.prod.yaml restart web

# Retry email immediately
docker compose --env-file .env.production -f compose.prod.yaml exec web python manage.py retry_failed_email

# Stop services without deleting data
docker compose --env-file .env.production -f compose.prod.yaml down
```

Do not use `docker compose down -v` in production: `-v` deletes named volumes containing the database, media, certificates, and other persistent data.

## Troubleshooting PostgreSQL password authentication

The PostgreSQL image reads `POSTGRES_PASSWORD_FILE` only when it initializes an
empty data directory. Replacing `secrets/postgres_password.txt` later does not
change the password stored for an existing PostgreSQL role.

First confirm the host and both containers see the same secret without printing it:

```bash
sha256sum secrets/postgres_password.txt
docker compose --env-file .env.production -f compose.prod.yaml exec db sha256sum /run/secrets/postgres_password
docker compose --env-file .env.production -f compose.prod.yaml run --rm --no-deps web sha256sum /run/secrets/postgres_password
```

All three hashes must match. If they match but PostgreSQL reports `password
authentication failed`, synchronize the existing role with the mounted secret:

```bash
docker compose --env-file .env.production -f compose.prod.yaml exec db sh -eu -c '
  new_password=$(cat /run/secrets/postgres_password)
  psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=on \
    --command "ALTER ROLE powerpayerp WITH PASSWORD '\''${new_password}'\'';"
'
```

The generated passwords documented in this runbook use Base64 characters and do
not contain single quotes. If a manually chosen password may contain a single
quote, generate a new password with the documented `openssl rand -base64` command
before synchronizing it.

Recreate the application containers afterward; do not delete the database volume:

```bash
docker compose --env-file .env.production -f compose.prod.yaml up -d --force-recreate web email-retry
docker compose --env-file .env.production -f compose.prod.yaml run --rm web python manage.py migrate
```
