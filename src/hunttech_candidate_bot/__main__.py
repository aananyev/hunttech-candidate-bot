"""
HuntTech Candidate Bot — entry point for python -m hunttech_candidate_bot
"""
from hunttech_candidate_bot.main import main

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())