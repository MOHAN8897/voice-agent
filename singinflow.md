🔐 Secure Login Rules
1. Use HTTPS everywhere

Mandatory:

https://yourdomain.com

Never allow production authentication over HTTP.

Also enable:

TLS
HSTS
Secure cookies
No mixed HTTP/HTTPS authentication resources

OWASP specifically recommends TLS for the entire authenticated session, not just the login page.

2. Never trust the frontend for authentication

This is one of the most important rules.

❌ Don't do:

Frontend:
if (user.isLoggedIn) {
    showDashboard();
}

and consider that sufficient security.

The backend must independently verify authentication on every protected API request.

Browser
   ↓
API request
   ↓
Backend
   ↓
Verify session
   ↓
Verify user
   ↓
Verify authorization
   ↓
Return data

The frontend is only a UI.

3. Use a server-side session

For a normal web application, prefer:

HttpOnly + Secure + SameSite cookie

rather than putting long-lived authentication tokens in:

localStorage
sessionStorage
URL parameters

Session identifiers need to be unpredictable and protected because possession of a valid session can effectively give an attacker the user's authenticated state.

Example:

Set-Cookie:
  session=RANDOM_SECURE_VALUE;
  HttpOnly;
  Secure;
  SameSite=Lax;
  Path=/

For a sensitive cross-site architecture, choose SameSite deliberately based on your actual flow rather than blindly copying a value.

4. Generate your own internal User ID

Don't use email as your database primary key.

Use something like:

users
-------------------------
id: UUID
email: user@example.com
email_verified: true
created_at: ...

The user ID should be randomly generated rather than predictable/sequential.

5. Email + password flow

Your flow should be:

Signup
  ↓
Email
  ↓
Password
  ↓
Create account
  ↓
Send verification email
  ↓
User verifies email
  ↓
Account activated
  ↓
Login
  ↓
Create secure session
Password rules

Don't create your own password hashing algorithm.

Use a modern password hashing algorithm such as:

Argon2id

or another properly configured password-hashing implementation supported by your authentication framework.

Allow long passphrases. OWASP recommends a maximum accepted password length of at least 64 characters and emphasizes length/blocklist controls rather than arbitrary complexity rules.

6. Never store passwords as plaintext

Absolutely never:

password = "Sai123"

or:

password_hash = SHA256(password)

as your password storage design.

Instead:

password
   ↓
Argon2id
   ↓
password_hash
   ↓
database

The database should contain the password hash, not the original password.

7. Email verification is mandatory

When somebody creates:

abc@example.com

don't immediately treat the address as verified.

Use:

verification token
        ↓
email
        ↓
user clicks
        ↓
backend verifies token
        ↓
email_verified = true

The verification token should be:

cryptographically random
short-lived
single-use
invalidated after successful use
8. Forgot-password flow must be extremely careful

Correct:

Forgot password
       ↓
Enter email
       ↓
Generic response
       ↓
Send reset email if account exists
       ↓
Random single-use token
       ↓
Short expiration
       ↓
Reset password
       ↓
Invalidate token
       ↓
Invalidate/revoke existing sessions
       ↓
Login again

Don't reveal:

❌ "This email doesn't exist."

because attackers can use that to enumerate accounts.

Instead:

"If an account exists for this email,
we've sent password-reset instructions."
9. Protect login against brute force

Never allow:

POST /login

password attempt #1
password attempt #2
password attempt #3
...
password attempt #1,000,000

Implement:

rate limiting
progressive delays
IP/device abuse detection
credential stuffing detection
monitoring
appropriate temporary throttling

OWASP specifically recommends login throttling to defend against automated password guessing.

Don't make permanent account lockout your only defense, because attackers can abuse lockouts to deny service to legitimate users.

10. Prevent account enumeration

These should not expose whether an account exists:

/login
/signup
/forgot-password

For example, avoid:

❌ "Email exists."
❌ "Wrong password."
❌ "No account found."

Use sufficiently generic responses where revealing account existence isn't necessary.

11. Google Sign-In must use OpenID Connect correctly

For Google authentication, you're doing authentication with OpenID Connect (OIDC), not simply "OAuth login."

The backend should validate the Google ID token.

At minimum verify:

iss
aud
signature
exp

OWASP specifically recommends validation of issuer, audience, signature and expiration for OIDC ID tokens.

12. Never trust an email address sent by the browser

This is a huge rule.

❌ Never do:

{
  "email": "victim@gmail.com"
}

and then:

"Okay, this is the user."

Instead:

Google
 ↓
Signed ID token
 ↓
Backend
 ↓
Verify token
 ↓
Extract Google subject (`sub`)
 ↓
Find/create user
 ↓
Create your session
13. Don't identify Google users only by email

For Google accounts, maintain the provider identity.

Example:

users
-------------------------
id
email
email_verified

identities
-------------------------
user_id
provider = google
provider_subject = Google's `sub`

Use Google's stable subject identifier (sub) as the provider-specific identity key.

Conceptually:

Google account
      ↓
Google `sub`
      ↓
Your identity record
      ↓
Your internal user_id

This prevents your application's identity system from depending solely on an email string.

14. OAuth redirect URLs must be exact

Don't allow:

https://yourdomain.com/*

as a generic OAuth redirect.

Register exact legitimate redirect URIs.

Google applies validation rules to OAuth redirect URIs and requires HTTPS for production redirect URIs, with localhost exceptions for development.

Example:

https://app.example.com/auth/google/callback

Not:

https://example.com/anything
15. Use state / nonce correctly

Your Google login transaction needs protection against login-CSRF / authorization-response injection.

For OAuth/OIDC, use appropriate transaction-bound:

state
nonce

and, where applicable:

PKCE

OWASP recommends transaction-specific values securely bound to the user's browser/session.

Conceptually:

User clicks Google Login
        ↓
Generate transaction
        ↓
state + nonce (+ PKCE where applicable)
        ↓
Google
        ↓
Callback
        ↓
Verify state/nonce
        ↓
Verify ID token
        ↓
Create session
16. Never put OAuth secrets in frontend code

❌ Never:

const GOOGLE_CLIENT_SECRET = "xxxxx";

inside React/Next.js/browser code.

Frontend:

GOOGLE_CLIENT_ID

may be public depending on the flow.

Backend secrets:

GOOGLE_CLIENT_SECRET

must remain server-side when your chosen flow requires one.

Also don't commit secrets into Git.

Use:

Environment variables
Secret Manager
17. Rotate sessions after login

Don't keep the anonymous session after authentication.

Correct:

Anonymous session
       ↓
Successful login
       ↓
Destroy/rotate old session
       ↓
Create new authenticated session

OWASP specifically recommends establishing a new session identifier after login and reauthentication.

This protects against session fixation.

18. Logout must actually invalidate the session

Don't just do:

localStorage.removeItem("user")

Your backend should invalidate/revoke the authenticated session.

Logout
  ↓
Invalidate server session
  ↓
Clear authentication cookie
  ↓
Redirect to login

OWASP recommends that logout fully terminate the associated session.

19. Protect sensitive account changes

For operations such as:

Change password
Change email
Delete account
Change payment information
Change security settings

require recent authentication/re-authentication where appropriate.

For example:

User logged in 6 hours ago
        ↓
Changes password
        ↓
Require password / reauthentication
        ↓
Allow change

OWASP recommends reauthentication for sensitive operations and risk events.

20. Email change requires verification

Don't simply allow:

old@example.com
       ↓
new@example.com
       ↓
database update

Use a controlled verification process.

For example:

User requests email change
        ↓
Reauthenticate
        ↓
Send verification to new address
        ↓
Verify
        ↓
Change email
        ↓
Notify old address
        ↓
Invalidate sensitive sessions if appropriate
21. CSRF protection

If authentication uses cookies, protect state-changing requests against CSRF.

Especially:

POST
PUT
PATCH
DELETE

for things like:

change password
change email
delete account
change subscription

Use an appropriate combination of:

SameSite cookies
CSRF tokens where required
origin/referer validation where appropriate
server-side authorization
22. XSS protection

An XSS vulnerability can destroy an otherwise excellent authentication design.

Use:

Content Security Policy
Output encoding
Input validation
Trusted framework escaping
Safe HTML handling

Don't render arbitrary user content as raw HTML.

23. Don't put sessions in URLs

Never:

https://example.com/dashboard?token=SECRET

URLs can leak through browser history, logs, referrers and other mechanisms. OWASP specifically warns about session identifiers in URLs.

24. Don't log passwords or tokens

Your logs should never contain:

password
password reset token
session token
Google ID token
refresh token
OAuth client secret

Bad:

LOGIN token=eyJhbGciOi...

Good:

LOGIN user_id=8b31... success=true

with appropriate privacy controls.

25. Database authorization must be separate from authentication

Being logged in doesn't mean the user can access everything.

Always check:

Authentication
      ↓
Who are you?
      ↓
Authorization
      ↓
What are you allowed to access?

Example:

GET /api/users/123

authenticated = true
        ↓
Does current_user.id == 123?
        ↓
OR
Does current_user have permission?
        ↓
Allow / deny

Never rely on:

Frontend route protection

for authorization.

26. Prevent IDOR

This is especially important for SaaS.

Don't assume:

GET /api/project/123

is safe simply because the user is logged in.

Check ownership:

project 123
     ↓
belongs_to user 456?
     ↓
current user = 456?
     ↓
YES → return
NO  → 403/404
27. Use secure cookies

For your main authentication cookie:

HttpOnly = true
Secure = true
SameSite = appropriate
Path = /

Keep cookie scope as narrow as practical.

OWASP recommends appropriately restricted cookie domain/path settings and secure cookie handling.

28. Keep authentication errors generic

Don't return detailed security information to attackers.

Instead of:

❌ Google account exists but isn't linked
❌ Password is correct but email isn't verified
❌ Account exists

use appropriate generic responses where revealing those details isn't necessary.

But your internal logs can contain the detailed diagnostic information needed for security monitoring.

29. Monitor authentication events

Log security-relevant events such as:

LOGIN_SUCCESS
LOGIN_FAILURE
GOOGLE_LOGIN_SUCCESS
GOOGLE_LOGIN_FAILURE
PASSWORD_RESET_REQUEST
PASSWORD_RESET_SUCCESS
PASSWORD_CHANGE
EMAIL_CHANGE
SESSION_REVOKED
SUSPICIOUS_LOGIN

Don't log secrets.

OWASP recommends logging and monitoring authentication failures and lockouts.

30. Add account/session management

Your account page should ideally allow:

Account
 ├── Profile
 ├── Email
 ├── Password
 ├── Connected Google account
 ├── Active sessions
 ├── Logout
 └── Logout all devices

For example:

Chrome — Hyderabad — Active
Firefox — Mumbai — 2 hours ago
Mobile — Android — yesterday

[Logout all other sessions]

This becomes extremely useful if a session is stolen.

31. Don't automatically merge accounts dangerously

Suppose someone has:

Email/password:
john@gmail.com

and then Google says:

john@gmail.com

Don't blindly merge identities solely because a browser supplied the same email.

Use verified provider identity and an explicit account-linking process.

Conceptually:

Existing account
       ↓
User proves ownership
       ↓
Google authentication
       ↓
Explicit "Link Google"
       ↓
Google identity attached
32. Don't automatically link arbitrary Google identities

Maintain:

User
 ├── Email/password
 └── Google identity

as separate authentication methods attached to the same internal user.

That gives you:

user_id = 123

identities:
  password → yes
  google   → Google sub XYZ

rather than creating multiple unrelated users unnecessarily.

33. Password reset should revoke sessions

If someone successfully changes a password through account recovery:

Password reset
      ↓
Update password hash
      ↓
Invalidate reset token
      ↓
Revoke existing sessions
      ↓
Require login again

This helps prevent a previously stolen session from remaining useful.

34. Google login should end with YOUR session

Don't let your entire application depend on the Google token forever.

Prefer:

Google
  ↓
Google authentication
  ↓
Backend verifies Google identity
  ↓
Find/create your user
  ↓
Create YOUR application session
  ↓
Your API

This gives you one consistent authorization layer for:

Email login
Google login
35. Use one user model for both login methods

Your database should conceptually look like:

USER
│
├── id
├── email
├── email_verified
├── created_at
└── status

AUTH_IDENTITIES
│
├── user_id
├── provider
├── provider_subject
└── created_at

Example:

USER
id = 123
email = sai@example.com

AUTH_IDENTITIES

user_id = 123
provider = password

user_id = 123
provider = google
provider_subject = 1098237...

Now both:

Email login
     ↓
user 123

Google login
     ↓
user 123

can access the same account.

🧪 Your final security test checklist

Before putting the login system into production, test these.

Email