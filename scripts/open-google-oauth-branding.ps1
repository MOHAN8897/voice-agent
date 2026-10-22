# Google shows "Sign in to venuefinder" when OAuth consent screen App name is still the old project name.
# Fix in Cloud Console (cannot be changed from Voxly code):
$project = "gen-lang-client-0799442928"
$url = "https://console.cloud.google.com/auth/branding?project=$project"
Write-Host @"
Update Google OAuth branding for Voxly:
  1. App name: Voxly AI
  2. User support email: your email
  3. App logo: optional
  4. Save

Also add test users (Testing mode): mohansaiteja.99@gmail.com

Opening: $url
"@
Start-Process $url
