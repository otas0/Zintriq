"""GAP 2: Verify removed Firebase routes return 404."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import app

# Check if routes exist in URL map
print("Checking URL map for removed Firebase routes:")
print("-" * 60)

routes_to_test = [
    '/auth/firebase',
    '/auth/firebase/customer',
    '/account/onboarding/google'
]

url_rules = [rule.rule for rule in app.url_map.iter_rules()]

for route in routes_to_test:
    exists = route in url_rules
    status = "EXISTS (ERROR!)" if exists else "NOT FOUND (correct)"
    print(f"{route:40s} → {status}")

print("-" * 60)
print("All routes should NOT exist in URL map")

# Also test with test_client using GET
print("\nTesting with GET requests:")
print("-" * 60)
client = app.test_client()

for route in routes_to_test:
    r = client.get(route)
    print(f"{route:40s} → {r.status_code}")

print("-" * 60)
print("404 = route doesn't exist (correct)")
print("405 = route exists but wrong method (ERROR!)")
