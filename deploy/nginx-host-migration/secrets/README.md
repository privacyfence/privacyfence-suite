Put the OIDC client secret of your identity provider in `idp_client_secret` (the only file here that is used).
It is the file `privacyfence-app --print-env-from-bundle --idp-secret-file PATH` wrote in step 1 of the
migration. With PrivacyFence's built-in Google sign-in there is no secret and this folder stays empty.
