import time

from securesync.models import Device


def gen_claim_token(org_id, expires=None, type='claim_zone'):
    token = {}
    if not expires:
        token['expires'] = str(time.time())
    else:
        if not isinstance(expires, float):
            raise TypeError('expires parameter must be a float.')
        token['expires'] = expires

    token['org_id'] = str(org_id)
    token['signature'] = _sign_token(token)
    return token

def verify_token(token):
    key = Device.get_own_device().get_key()
    signature = token.pop('signature')
    return key.verify(str(token), signature)

def _sign_token(token):
    key = Device.get_own_device().get_key()
    return key.sign(str(token)) # assumes there is no signature in the token yet
