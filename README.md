# Letterboxd × JustWatch AR

Script automático que sincroniza tu watchlist de Letterboxd con disponibilidad en JustWatch Argentina.

## Setup

### 1. Fork o creá este repositorio en GitHub

### 2. Conseguí tus cookies de Letterboxd
1. Abrí Chrome/Firefox y andá a letterboxd.com
2. Iniciá sesión con tu cuenta
3. Abrí DevTools (F12) → Application → Cookies → letterboxd.com
4. Copiá el valor de `com.xk72.webparts.csrf`
5. Copiá el valor de `letterboxd.signed.in`

### 3. Creá credenciales de Google
1. Andá a console.cloud.google.com
2. Creá un proyecto nuevo
3. Habilitá Google Sheets API y Google Drive API
4. Creá una Service Account
5. Descargá el JSON de credenciales
6. Compartí el Sheet con el email de la Service Account

### 4. Configurá los Secrets en GitHub
En tu repo → Settings → Secrets and variables → Actions → New repository secret:
- `LB_CSRF`: valor de la cookie `com.xk72.webparts.csrf`
- `LB_SESSION`: valor de la cookie `letterboxd.signed.in`
- `GOOGLE_CREDENTIALS`: contenido completo del JSON de credenciales de Google

### 5. Activá GitHub Actions
El script corre automáticamente todos los lunes a las 10am (Argentina).
Para correrlo manualmente: Actions → Letterboxd × JustWatch Sync → Run workflow
