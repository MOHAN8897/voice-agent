import asyncio
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from server.db.connection import init_db, get_session_factory
from sqlalchemy import text

async def reset_onboarding(email: str = 'saiskm115@gmail.com'):
    await init_db()
    factory = get_session_factory()
    if not factory:
        print("Database not configured, skipping reset.")
        return
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM user_onboarding_surveys WHERE user_id IN (SELECT user_id FROM users WHERE email = :email)"),
                {"email": email}
            )
    print(f"Successfully reset onboarding survey for {email}")

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'saiskm115@gmail.com'
    asyncio.run(reset_onboarding(target))
