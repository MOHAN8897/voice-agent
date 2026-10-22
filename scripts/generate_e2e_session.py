import json
from server.auth.jwt_tokens import AccessTokenClaims, create_access_token

claims = AccessTokenClaims(
    user_id="41cdd149-9e55-4e5a-b4b6-f2f1f02172c2",
    tenant_id="6d3fba56-7109-4812-8eb5-4a0d11f558c6",
    role="platform_admin",
    email="mohansaiteja.99@gmail.com",
)
token, exp = create_access_token(claims, ttl_seconds=86400)
session_data = {
    "token": token,
    "user": {
        "userId": "41cdd149-9e55-4e5a-b4b6-f2f1f02172c2",
        "email": "mohansaiteja.99@gmail.com",
        "fullName": "Mohan Saiteja",
        "status": "active",
        "emailVerified": True,
        "hasCompletedOnboarding": True,
    },
    "tenant": {
        "tenantId": "6d3fba56-7109-4812-8eb5-4a0d11f558c6",
        "name": "mohan saiteja's Workspace",
    },
    "agentId": "832dd86c-bbd5-4bcc-8466-469b3411c99f",
}
with open("data/e2e_session.json", "w") as f:
    json.dump(session_data, f, indent=2)
print("e2e_session.json updated successfully! Token exp:", exp)
