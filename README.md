# Joseph Login System (Flask + Firebase)

Login system gamit ang **Flask**, **Firebase Authentication** (Email/Password), at **Cloud Firestore**. May register, login, logout, at protected dashboard.

- Password handling → Firebase Authentication (si Google ang nagha-hash, hindi naka-save sa app).
- Profile details (username, full name) → Cloud Firestore (`users/{uid}`).
- Session → secure HttpOnly session cookie mula sa Firebase Admin SDK.

## Mga file

| File | Layunin |
| --- | --- |
| `app.py` | Flask app at mga route (login, register, logout, dashboard) |
| `firebase_db.py` | Firebase Auth + Firestore functions |
| `.env.example` | Template ng settings (kopyahin to `.env`) |
| `templates/` | HTML pages (`base`, `login`, `register`, `dashboard`) |
| `static/style.css` | Design ng mga page |
| `requirements.txt` | Mga kailangang package |
| `serviceAccountKey.json` | **Ikaw ang magdadagdag** (secret, huwag i-commit) |

## Setup sa Firebase Console (step-by-step)

1. Pumunta sa <https://console.firebase.google.com> at **Add project** (hal. `joseph-login`).
2. Sa project, i-click ang **Web** icon (`</>`) para mag-add ng web app. Kopyahin ang **`apiKey`** sa `firebaseConfig` — ito ang `FIREBASE_API_KEY`.
3. **Authentication** → **Sign-in method** → **Email/Password** → **Enable** → Save.
4. **Firestore Database** → **Create database** → piliin ang **Production mode** at region → Create.
5. **Project settings** (gear icon) → **Service accounts** → **Generate new private key**.
6. I-rename ang na-download na `.json` file to **`serviceAccountKey.json`** at ilagay sa loob ng `C:\Users\suete\Documents\joseph`.

> Huwag ibigay o i-post ang `serviceAccountKey.json` — full access iyon sa Firebase project mo.

### Firestore security rules (importante)

Dahil server-side (Admin SDK) ang app, pwede mong i-block ang direct client access. Sa **Firestore → Rules**, ilagay:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

Hindi ito naaapektuhan ang app mo dahil ang Admin SDK ay lumalampas sa rules.

## Setup sa computer

1. **Gawin ang `.env`:**

   ```powershell
   cd C:\Users\suete\Documents\joseph
   Copy-Item .env.example .env
   notepad .env
   ```

   Ilagay ang `FIREBASE_API_KEY` mula sa step 2 sa itaas.

2. **Install ang mga package:**

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **I-check ang setup:**

   ```powershell
   python check_firebase.py
   ```

4. **Patakbuhin:**

   ```powershell
   python app.py
   ```

5. Buksan ang <http://127.0.0.1:5000> at i-click ang **Mag-register** para gumawa ng account.

Walang default account — ikaw ang unang magre-register.

## Roles: user at admin

Bawat account ay may `role` sa Firestore (`users/{uid}.role`):

- **user** — makikita lang ang sariling dashboard.
- **admin** — may access sa **Admin dashboard** (`/admin`) kung saan puwedeng:
  - tingnan ang lahat ng account at statistik,
  - i-promote ang user sa admin (o i-demote pabalik),
  - burahin ang account (Firebase Auth + Firestore profile).

**Ang unang account na magre-register ay automatic na admin.** Kapag may admin na, lahat ng bagong register ay `user`.

Kung may existing account na dapat maging admin, patakbuhin:

```powershell
python make_admin.py <username-o-email>
```

Mga proteksyon na naka-built in:

- Hindi mo puwedeng baguhin o burahin ang sariling role/account sa admin panel.
- Hindi mababago o mabubura ang **huling admin** (para hindi mawalan ng access).
- Ang admin check ay server-side (Firestore profile) — hindi lang nakatago sa UI.

## Paano gumagana

1. **Register** → gumagawa ng user sa Firebase Authentication (`create_user`) at profile document sa Firestore (`users/{uid}`).
2. **Login** → hinahanap sa Firestore ang email ng username, tapos nag-sign in sa Firebase Auth (REST `signInWithPassword`) at gumagawa ng session cookie (`create_session_cookie`).
3. **Bawat page** → vine-verify ang session cookie (`verify_session_cookie`) bago pakita ang dashboard.
4. **Logout** → nire-revoke ang refresh tokens at nililinis ang Flask session.

## Troubleshooting

| Problema | Solusyon |
| --- | --- |
| “Hindi pa naka-setup ang Firebase” | Kulang ang `serviceAccountKey.json` o `FIREBASE_API_KEY` sa `.env`. |
| `API key not valid` | Mali ang `FIREBASE_API_KEY`; kopyahin ulit sa Project settings → General. |
| `403` / `PERMISSION_DENIED` sa Firestore | Hindi pa na-create ang Firestore database sa console. |
| `auth/operation-not-allowed` | Hindi pa naka-enable ang **Email/Password** sign-in method. |
| Nag-logout bigla | 5 araw ang session cookie (`SESSION_DAYS` sa `firebase_db.py`). |

## Tandaan

- Palitan ang `SECRET_KEY` sa `.env` ng mahabang random string.
- `.env` at `serviceAccountKey.json` ay nasa `.gitignore` — hindi sila dapat ma-commit.
