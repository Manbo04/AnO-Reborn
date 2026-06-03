import os
import sys
import json
import urllib.request
import time

TOKEN = "rw_Fe26.2**13a534d682a356b16fc581fe3571adafbfc3fc31fe0372f5eae495987f1b3341*DYwZuP-Zxj1Byc4sCLtbUg*mlOxC3rwVMEDC5msL_6jlpvXMWcTzkiJGx0gv3So1UE9qnimMvzJL3xkhh7peGXRIj7cLEtcpxotLQgPsMrEPw*1781889391930*c7436faf6b69f84424161f23fa92a744173466e146796911a8e0dd910b25c85f*egCXV341RQsf50mqFjns50hRhfkETnXEGuG2ZucitqA"

def graphql(query, variables=None):
    req = urllib.request.Request(
        "https://backboard.railway.app/graphql/v2",
        data=json.dumps({"query": query, "variables": variables or {}}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
        return None

def main():
    # Target volume instance (prod-validator in production): 278c8ba9-4ea6-4afb-a132-56aba476d199
    volInstId = "278c8ba9-4ea6-4afb-a132-56aba476d199"
    backupId = "8bd8e5bf-c073-4a71-b8d9-52188a8404b4" # May 31
    
    q_rest = """
    mutation RestoreBackup($backupId: String!, $targetId: String!) {
      volumeInstanceBackupRestore(volumeInstanceBackupId: $backupId, volumeInstanceId: $targetId) {
        workflowId
      }
    }
    """
    res = graphql(q_rest, {"backupId": backupId, "targetId": volInstId})
    print(f"Restore triggered: {res}")
    
    print("Waiting 120s for restoration...")
    time.sleep(120)
    
    # Redeploy
    q_dep = """
    mutation Redeploy($envId: String!, $svcId: String!) {
      serviceInstanceRedeploy(environmentId: $envId, serviceId: $svcId)
    }
    """
    graphql(q_dep, {"envId": "e60f87d0-5b60-4036-98fb-03eb0caa61e6", "svcId": "a3c62c3c-ddaf-4319-aa56-255c0b557fde"})
    print("Redeploy triggered.")

if __name__ == "__main__":
    main()
