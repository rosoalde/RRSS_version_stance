
from mastodon import Mastodon, StreamListener
import time

class TestListener(StreamListener):
    def on_update(self, status):
        print("✅ Toot:", status.get("content", "no content")[:100])

    def on_abort(self, err):
        print("🔄 ABORT:", repr(err))

mastodon = Mastodon(
    access_token="iLzW0jLj35210PxMFuKl9Rpb_4KyJYjpPfSiji4XhTE",
    api_base_url="https://mastodon.social",
)

# Prueba API normal ANTES del streaming
try:
    me = mastodon.account_verify_credentials()
    print("✅ TOKEN VÁLIDO. Usuario:", me['username'], me['acct'])
except Exception as e:
    print("❌ TOKEN INVÁLIDO:", e)
    exit(1)


print("🔗 Connected to Mastodon")

# Bucle que ignora el primer evento vacío y sigue
while True:
    try:
        mastodon.stream_public(TestListener(), timeout=None)
    except Exception as e:
        print("🔄 Reconnecting in 2s:", repr(e))
        time.sleep(2)
