#!/bin/bash
# Creates the security certificate Betfair needs for bot logins (certs/client-2048.crt + .key).
# Upload certs/client-2048.crt to Betfair: My Account > Security > Automated Betting Program Access > Edit.
cd "$(dirname "$0")"
mkdir -p certs && cd certs
if [ -f client-2048.crt ]; then echo "certs/client-2048.crt already exists."; exit 0; fi
cat > openssl.cnf <<'CNF'
[ req ]
distinguished_name = dn
[ dn ]
[ ssl_client ]
basicConstraints = CA:FALSE
nsCertType = client
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
CNF
openssl genrsa -out client-2048.key 2048
openssl req -new -config openssl.cnf -key client-2048.key -out client-2048.csr -subj "/C=GB/CN=racing-paper-bot"
openssl x509 -req -days 365 -in client-2048.csr -signkey client-2048.key -out client-2048.crt -extfile openssl.cnf -extensions ssl_client
chmod 600 client-2048.key
echo
echo "Done. Upload this file to Betfair:  $(pwd)/client-2048.crt"
open . 2>/dev/null
