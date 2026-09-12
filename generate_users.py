#!/usr/bin/env python3
import getpass, hashlib, json, os, sys
users=[]
for argument in sys.argv[1:]:
    username, role = argument.split(":", 1)
    if role not in ("read", "write"): raise SystemExit("role must be read or write")
    password=getpass.getpass("Password for %s: " % username)
    if password != getpass.getpass("Confirm password: "): raise SystemExit("passwords do not match")
    salt=os.urandom(16).hex(); iterations=200000
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),iterations).hex()
    users.append({"username":username,"role":role,"passwordHash":"pbkdf2_sha256$%d$%s$%s"%(iterations,salt,digest)})
print(json.dumps({"users":users}, indent=2))
