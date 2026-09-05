"""Wait for startup probes to finish; exit nonzero on failure."""
import sys
import time
import httpx
from qa_agent.config import DEMO_ORIGIN


def main():
    deadline=time.monotonic()+45
    with httpx.Client(base_url=DEMO_ORIGIN,timeout=2) as client:
        while time.monotonic()<deadline:
            try:
                client.get('/')
                response=client.get('/api/readiness')
                result=response.json()
                if response.status_code==200 and result.get('ready'):
                    print(f'Aviar ready: {DEMO_ORIGIN} (browser and data access verified)')
                    return 0
                if response.status_code==503:
                    for error in result.get('errors',[]):print(f"{error['code']} at {error['stage']}: {error['message']}\n{error['remedy']}",file=sys.stderr)
                    return 1
            except (httpx.HTTPError,ValueError):pass
            time.sleep(.5)
    print('Server did not become ready within 45 seconds. Inspect data/server.stderr.log.',file=sys.stderr)
    return 1


if __name__=='__main__':raise SystemExit(main())
