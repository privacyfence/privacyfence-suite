Put the OIDC client secret of your identity provider in `idp_client_secret` (the only file here that is used).
Create it with `install -m 0600 /dev/null secrets/idp_client_secret`, then paste the value into it.
With PrivacyFence's built-in Google sign-in there is no secret and this folder stays empty.
